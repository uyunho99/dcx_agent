"""Cluster-local keyword SNA. New artifacts contain only the six v2 fields."""
import json
import re
from datetime import datetime
from itertools import combinations

import numpy as np

from app.services.s3 import load_data, save_json, load_json, list_objects
from app.jobs.manager import job_manager


def latest_artifact(prefix: str, stem: str, suffix: str) -> str | None:
    keys = [obj['Key'] for obj in list_objects(prefix)
            if obj['Key'].startswith(prefix + stem) and obj['Key'].endswith(suffix)]
    return max(keys, default=None)


def cooccurrence_matrix(documents: list[dict]) -> tuple[list[str], np.ndarray]:
    """One undirected edge per distinct keyword pair per document; no self loops.

    Explicit keywords take precedence; legacy kw strings are tokenized if absent.
    No cluster-level vocabulary is copied into individual documents.
    """
    keyword_sets = []
    for doc in documents:
        words = doc.get('keywords')
        if words is None:
            words = re.findall(r'\w+', doc.get('kw') or '')
        if not isinstance(words, list) or any(not isinstance(w, str) for w in words):
            raise ValueError('keywords must be a list of strings')
        keyword_sets.append(sorted({w.strip() for w in words if w.strip()}))
    terms = sorted(set().union(*keyword_sets)) if keyword_sets else []
    indices = {term: i for i, term in enumerate(terms)}
    adjacency = np.zeros((len(terms), len(terms)), dtype=float)
    for words in keyword_sets:
        for a, b in combinations(words, 2):
            i, j = indices[a], indices[b]
            adjacency[i, j] += 1
            adjacency[j, i] += 1
    return terms, adjacency


def eigenvector_centrality(adjacency: np.ndarray) -> np.ndarray:
    """L2-normalized principal eigenvector, including disconnected graphs.

    Project a uniform vector onto the dominant eigenspace so equal disconnected
    components do not depend on the eigensolver's arbitrary basis selection.
    Edgeless graphs use uniform scores (every vector is a zero eigenvector).
    """
    n = len(adjacency)
    if not n:
        return np.array([], dtype=float)
    if not adjacency.any():
        return np.ones(n) / np.sqrt(n)
    values, vectors = np.linalg.eigh(adjacency)
    dominant = vectors[:, np.isclose(values, values[-1], rtol=1e-10, atol=1e-12)]
    scores = np.maximum(dominant @ (dominant.T @ np.ones(n)), 0)
    return scores / np.linalg.norm(scores)


def modularity_partition(adjacency: np.ndarray) -> tuple[list[list[int]], float]:
    """Deterministic greedy positive-gain weighted modularity (resolution 1).

    Q = sum_C (internal_weight_C / m - (degree_C / (2m))**2).
    Isolated vertices remain singleton communities; no-edge Q is defined as 0.
    """
    groups = [[i] for i in range(len(adjacency))]
    total = float(adjacency.sum())  # 2m
    if not total:
        return groups, 0.0
    edges = adjacency / total
    fractions = edges.sum(axis=1)
    while len(groups) > 1:
        gain = 2 * (edges - np.outer(fractions, fractions))
        gain[np.tril_indices(len(groups))] = -np.inf
        i, j = np.unravel_index(np.argmax(gain), gain.shape)
        if gain[i, j] <= 1e-12:
            break
        groups[i] = sorted(groups[i] + groups[j])
        del groups[j]
        # Coarsen the normalized adjacency, retaining internal edge weight.
        edges[i, :] += edges[j, :]
        edges[:, i] += edges[:, j]
        edges = np.delete(np.delete(edges, j, axis=0), j, axis=1)
        fractions = edges.sum(axis=1)
    q = float(np.trace(edges) - np.dot(fractions, fractions))
    return sorted(groups, key=lambda g: g[0]), q


def generate_personas(clusters: list[dict], records: list[dict]) -> list[dict]:
    """Validate T6 membership before analysis; never pool different clusters.

    Desire/goals are keyword-based drafts, not human-confirmed interpretations.
    Cluster membership is encoded in persona_id under the six-field contract.
    """
    by_id = {}
    for doc in records:
        did = doc.get('doc_id')
        if not isinstance(did, str) or not did or did in by_id:
            raise ValueError('missing or duplicate source doc_id')
        by_id[did] = doc
    seen_clusters, seen_docs = set(), set()
    scoped = []
    for cluster in clusters:
        cid = cluster.get('cluster_id')
        if not isinstance(cid, str) or not re.fullmatch(r'CL\d+', cid) or cid in seen_clusters:
            raise ValueError('missing, invalid or duplicate cluster_id')
        seen_clusters.add(cid)
        documents = []
        for member in cluster['documents']:
            did = member.get('doc_id')
            if did not in by_id or did in seen_docs:
                raise ValueError(f'missing or duplicate cluster membership: {did}')
            seen_docs.add(did)
            documents.append(by_id[did])
        scoped.append((cid, documents))

    personas = []
    for cid, documents in sorted(scoped, key=lambda pair: int(pair[0][2:])):
        terms, adjacency = cooccurrence_matrix(documents)
        scores = eigenvector_centrality(adjacency)
        communities, q = modularity_partition(adjacency)
        for index, community in enumerate(communities or [[]], start=1):
            top = sorted(community, key=lambda i: (-round(float(scores[i]), 12), terms[i]))[:10]
            words = [terms[i] for i in top]
            personas.append({
                'persona_id': f'{cid}-P{index}',
                'desire': f'{", ".join(words[:3])} 관련 요구를 충족하고 싶다' if words else '',
                'goals': [f'{word} 관련 목표 구체화' for word in words[:3]],
                'centrality_top': [[terms[i], float(scores[i])] for i in top],
                'modularity_q': q,
                'status': 'draft' if words else 'insufficient_data',
            })
    return personas


def _load_source_records(key: str) -> list[dict]:
    # s3.py has no public load_jsonl. Its local load_data(file) scans the entire
    # parent directory, unlike S3's exact-key prefix. Keep this workaround local
    # until that shared adapter exposes an exact-file reader.
    from app.services import s3

    if s3._USE_LOCAL:
        return [json.loads(line) for line in s3._local_path(key).read_text(
            encoding='utf-8').splitlines() if line.strip()]
    return load_data(key)


def run_persona(config: dict) -> None:
    sid = config.get('sid', 's0')
    job_manager.set('persona', sid, {'status': 'running', 'progress': 0, 'phase': 'loading'})
    try:
        cluster_key = latest_artifact(f'clusters/{sid}/', 'result_', '.json')
        source_key = latest_artifact(f'classified/{sid}/', 'relevant_', '.jsonl')
        if not cluster_key or not source_key:
            raise ValueError('T6 cluster result and classified documents are required')
        artifact = load_json(cluster_key)
        if not artifact or not artifact.get('clusters'):
            raise ValueError('no clusters')
        if artifact.get('sid', sid) != sid or artifact.get('primary_method', 'embedding') != 'embedding':
            raise ValueError('expected this session’s embedding cluster result')
        records = _load_source_records(source_key)
        job_manager.update('persona', sid, progress=20, phase='sna')
        personas = generate_personas(artifact['clusters'], records)
        job_manager.update('persona', sid, progress=90, phase='saving')
        ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        result = {'schema_version': 2, 'sid': sid, 'timestamp': ts, 'personas': personas}
        save_json(f'personas/{sid}/result_{ts}.json', result)
        job_manager.set('persona', sid, {
            'status': 'done', 'progress': 100, 'phase': 'done', **result,
        })
    except Exception as exc:
        job_manager.set('persona', sid, {'status': 'error', 'phase': 'error', 'error': str(exc)})
