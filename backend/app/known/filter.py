"""Batched local RAG restricted to the active version's relevant documents."""
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3

import numpy as np

from app.config import settings
from app.context import store as sessions
from app.known import store
from app.known.models import read_known
from app.vectors.embedder import get_embedder, EmbedderUnconnected
from app.vectors.search import cosine_topk
from app.vectors.store import VectorStore


@dataclass
class SearchResult:
    # One ordered result list per input query (including empty query results).
    items: list[list[dict]]
    reason: str | None = None


def read_export(sid, data):
    ref = data.get('training', {}).get('exportRef')
    if not isinstance(ref, str) or not ref:
        raise sessions.StoreError('5단계 결과가 없습니다')
    base = (Path(settings.local_data_dir) / 'classified' / sid).resolve()
    path = (Path(settings.local_data_dir) / ref).resolve()
    # A version snapshot may deliberately inherit an earlier exportRef.
    # Read precisely that reference, bounded to this session's export tree.
    if not path.is_relative_to(base) or path.name != 'relevant.jsonl' or not path.is_file():
        raise sessions.StoreError('5단계 결과가 없습니다')
    return [doc for doc in read_jsonl(path) if doc.get('evidence_level_pred') in {'core', 'supporting'}]


def read_jsonl(path):
    with path.open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def prepared_documents(root):
    return {doc['doc_id']: doc for path in sorted((root / 'docs').glob('*.jsonl')) for doc in read_jsonl(path)}


def relevant_documents(sid, data, root):
    if data.get('training', {}).get('exportRef'):
        return {doc['doc_id']: doc for doc in read_export(sid, data)}
    path = sessions.session_dir(sid) / 'labels.sqlite'
    if not path.exists():
        return {}
    with sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True) as db:
        ids = {row[0] for row in db.execute("SELECT doc_id FROM final WHERE level IN ('core', 'supporting') AND (source='human' OR route IN ('accepted', 'audited'))")}
    return {key: doc for key, doc in prepared_documents(root).items() if key in ids}


def search_docs(sid, queries: list[str], top_k, novel=True) -> SearchResult:
    empty = [[] for _ in queries]
    with sessions.locked(sid):
        data = sessions.load_session(sid) or {}
        root = store.prepared_root(sid, data)
        if root is None:
            return SearchResult(empty, 'no_vectors')
        vectors = VectorStore(root)
        if not vectors.count():
            return SearchResult(empty, 'no_vectors')
        docs = relevant_documents(sid, data, root)
        if not docs:
            return SearchResult(empty, 'no_labels')
        valid = set()
        for ids, rows, failed in vectors.iter_shards():
            valid.update(doc_id for doc_id, row, bad in zip(ids, rows, failed)
                         if doc_id in docs and not bad and np.isfinite(row).all() and np.linalg.norm(row) > 0)
        if not valid:
            return SearchResult(empty, 'no_vectors')
        if not queries or top_k <= 0:
            return SearchResult(empty)
        try:
            query_vectors = store.session_embedder(sid, data, get_embedder).embed([query[:2000] for query in queries])
        except EmbedderUnconnected:
            return SearchResult(empty, 'embedder_unconnected')
        candidates = cosine_topk(vectors, query_vectors, top_k * 3, valid, set())
        known = read_known(data) if novel else []
        excluded = {item.doc_id for item in known if item.type == 'doc'}
        known_vecs = store.known_vectors(sid, known, vectors) if known else np.empty((0, settings.embed_dim))
        if len(known_vecs):
            norms = np.linalg.norm(known_vecs, axis=1)
            known_vecs = known_vecs[norms > 0] / norms[norms > 0, None]
        items = []
        removed = False
        for matches in candidates:
            kept = []
            ids, rows = vectors.get([doc_id for doc_id, score in matches])
            rows_by_id = dict(zip(ids, rows))
            for doc_id, score in matches:
                row = rows_by_id[doc_id]
                if doc_id in excluded or (len(known_vecs) and np.max(known_vecs @ (row / np.linalg.norm(row))) >= settings.known_theta):
                    removed = True
                    continue
                kept.append({**docs[doc_id], 'doc_id': doc_id, 'score': score})
            items.append(kept[:top_k])
        return SearchResult(items, 'all_known' if removed and not any(items) else None)
