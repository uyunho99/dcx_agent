"""STEP 07: embedding-owned IDs, Ward validation, and lossless band assignment.

Consumes the latest STEP 06 relevant snapshot with doc_id and embedding on every
record. Missing vectors are an upstream contract error, never silently re-embedded
or replaced with zeros. All distances/silhouettes use the supplied Euclidean space.
"""
from collections import Counter
from datetime import datetime
import json
import math
import re

import numpy as np
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_samples, silhouette_score

from app.jobs.manager import job_manager
from app.services import s3


def _latest_key(directory: str, stem: str, suffix: str) -> str | None:
    keys = [item["Key"] for item in s3.list_objects(directory)
            if item["Key"].startswith(directory + stem)
            and item["Key"].endswith(suffix)
            and "/" not in item["Key"][len(directory):]]
    return max(keys, default=None)


def _load_records(key: str) -> list[dict]:
    # s3 has no load_jsonl API yet. Its local load_data reads ALL siblings of
    # an existing file, unlike the S3 prefix reader. Keep this exact-key adapter
    # here until the shared storage API offers an exact JSONL reader.
    if s3._USE_LOCAL:
        return [json.loads(line) for line in (s3._DATA_DIR / key).read_text(
            encoding="utf-8").splitlines() if line.strip()]
    return s3.load_data(key)


def load_latest_result(sid: str) -> tuple[str, dict] | None:
    key = _latest_key(f"clusters/{sid}/", "result_", ".json")
    if key is None:
        return None
    result = s3.load_json(key)
    if not result:
        raise ValueError(f"Cannot read clustering result: {key}")
    return key, result


def result_status(key: str, result: dict) -> dict:
    return {**result, "status": "done", "phase": "complete", "progress": 100,
            "result_key": key, "num_clusters": result["selected_k"]}


def _validate(records: list[dict]) -> np.ndarray:
    if len(records) < 4:
        raise ValueError("STEP 07 requires at least 4 documents for k >= 3 silhouette")
    ids = [r.get("doc_id") for r in records]
    if any(not isinstance(doc_id, str) or not doc_id.strip() for doc_id in ids):
        raise ValueError("Every document requires a nonempty doc_id")
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate doc_id in STEP 06 snapshot")
    vectors = [r.get("embedding") for r in records]
    if any(not isinstance(v, list) or not v or any(
            isinstance(x, bool) or not isinstance(x, (int, float)) for x in v)
           for v in vectors):
        raise ValueError("Every document requires a numeric embedding from STEP 05/06")
    if len({len(v) for v in vectors}) != 1:
        raise ValueError("Embedding dimensions must match")
    matrix = np.asarray(vectors, dtype=float)
    if not np.isfinite(matrix).all():
        raise ValueError("Embeddings must contain only finite numbers")
    return matrix


def _tokens(record: dict) -> list[str]:
    keywords = record.get("keywords")
    if isinstance(keywords, list):
        return [word.strip() for word in keywords if isinstance(word, str) and word.strip()]
    # Upstream noun keywords are preferred. Without them, this is transparent
    # Unicode word tokenization, not a claim of Korean morphological analysis.
    text = record.get("text") or record.get("body") or " ".join(
        str(record.get(field, "")) for field in ("title", "desc", "kw"))
    return re.findall(r"\w+", text.lower(), flags=re.UNICODE)


def _class_tfidf(groups: list[list[dict]], top_n: int) -> list[list[list]]:
    # Golden contract: tf(class, term) * log(1 + mean class length / corpus tf).
    counts = [Counter(word for record in group for word in _tokens(record)) for group in groups]
    corpus = sum(counts, Counter())
    average_length = sum(corpus.values()) / len(groups)
    output = []
    for count in counts:
        length = sum(count.values())
        scores = [[word, frequency / length * math.log1p(average_length / corpus[word])]
                  for word, frequency in count.items()]
        output.append(sorted(scores, key=lambda pair: (-pair[1], pair[0]))[:top_n])
    return output


def _dominant_constraint(records: list[dict]) -> tuple[str, dict]:
    # No constraint formula is specified in the plan. Use an auditable proxy:
    # modal observed context, else category (including STEP 03's `cat`), else
    # collection keyword. Context is closest to the user's situation; keyword
    # is a weaker collection-context proxy, NOT an inferred pain/barrier.
    # Count each document once, lexical tie-break; expose missingness/strength
    # so a sparse context does not masquerade as a majority of all documents.
    for field in ("context", "category", "cat", "kw"):
        values = [r[field].strip() for r in records
                  if isinstance(r.get(field), str) and r[field].strip()]
        if values:
            value, count = min(Counter(values).items(), key=lambda pair: (-pair[1], pair[0]))
            return value, {"field": field, "count": count,
                           "coverage": len(values) / len(records), "share": count / len(records),
                           "method": "observed_metadata_mode"}
    return "unknown", {"field": None, "count": 0, "coverage": 0.0,
                       "share": 0.0, "method": "observed_metadata_mode"}


def _build_result(records: list[dict], sid: str, config: dict) -> dict:
    matrix = _validate(records)
    requested = config.get("num_clusters", 0)
    if type(requested) is not int or requested not in (0, *range(3, 15)):
        raise ValueError("num_clusters must be 0 (auto) or an integer in 3..14")
    top_n = config.get("top_n", 10)
    if type(top_n) is not int or top_n < 1:
        raise ValueError("top_n must be a positive integer")
    job_manager.update("cluster", sid, phase="k_scan", progress=10)
    unique_count = len(np.unique(matrix, axis=0))
    candidates, curve, unavailable = {}, [], []
    for k in range(3, 15):
        if k >= len(records) or k > unique_count:
            unavailable.append({"k": k, "reason": "requires k < document_count and k <= distinct_vectors"})
            continue
        labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(matrix)
        if len(set(labels)) != k:
            unavailable.append({"k": k, "reason": "kmeans produced fewer than k nonempty groups"})
            continue
        score = float(silhouette_score(matrix, labels))
        if not math.isfinite(score):
            raise ValueError("Nonfinite silhouette; check embedding magnitudes")
        candidates[k] = labels
        curve.append([k, score])
        job_manager.update("cluster", sid, progress=10 + (k - 2) * 4)
    if not curve:
        raise ValueError("No valid k in 3..14 for these embeddings")
    if requested and requested not in candidates:
        raise ValueError("Requested num_clusters cannot be scored on these embeddings")
    selected = requested or max(curve, key=lambda pair: (pair[1], -pair[0]))[0]
    raw_labels = candidates[selected]
    # Only this embedding branch allocates CL IDs, in first-document order.
    order = list(dict.fromkeys(raw_labels.tolist()))
    indices = [np.flatnonzero(raw_labels == label) for label in order]
    groups = [[records[int(i)] for i in positions] for positions in indices]
    terms = _class_tfidf(groups, top_n)
    silhouettes = silhouette_samples(matrix, raw_labels)
    job_manager.update("cluster", sid, phase="bands", progress=65)
    clusters = []
    for number, (positions, group, keywords) in enumerate(zip(indices, groups, terms)):
        centroid = matrix[positions].mean(axis=0)
        distances = np.linalg.norm(matrix[positions] - centroid, axis=1)
        p50, p90 = np.percentile(distances, [50, 90], method="linear")
        documents = [{**record, "cluster_id": f"CL{number}", "dist_centroid": float(distance),
                      "band": "core" if distance <= p50 else "fringe" if distance <= p90 else "edge"}
                     for record, distance in zip(group, distances)]
        band_counts = Counter(d["band"] for d in documents)
        constraint, basis = _dominant_constraint(group)
        clusters.append({
            "cluster_id": f"CL{number}", "label": " / ".join(word for word, _ in keywords[:3]) or f"CL{number}",
            "c_tfidf": keywords, "size": len(group),
            "authors": len({r["author_hash"] for r in group if r.get("author_hash")}),
            "centroid": centroid.tolist(), "silhouette": float(silhouettes[positions].mean()),
            "k_scan": curve, "bands": {band: band_counts[band] / len(group) for band in ("core", "fringe", "edge")},
            "band_thresholds": {"p50": float(p50), "p90": float(p90)},
            "documents": documents, "dominant_constraint": constraint, "dominant_constraint_basis": basis,
        })
    job_manager.update("cluster", sid, phase="ward_comparison", progress=80)
    ward_labels = AgglomerativeClustering(n_clusters=selected, linkage="ward").fit_predict(matrix)
    ward_score = float(silhouette_score(matrix, ward_labels))
    primary_score = dict(curve)[selected]
    return {
        "sid": sid, "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S_%f"),
        "primary_method": "embedding", "embedding_method": "kmeans", "total": len(records),
        "selected_k": selected, "selection_reason": "requested_num_clusters" if requested else
        "maximum_silhouette; ties_choose_smaller_k",
        "silhouette": primary_score, "k_scan": curve, "k_scan_unavailable": unavailable,
        "clusters": clusters,
        # Deliberate whitelist: neither input metadata nor primary IDs can leak.
        "ward": {"method": "ward", "k": selected, "silhouette": ward_score,
                 "documents": [{"doc_id": record["doc_id"], "label": int(label)}
                               for record, label in zip(records, ward_labels)]},
        "comparison": {"adjusted_rand_index": float(adjusted_rand_score(raw_labels, ward_labels)),
                       "silhouette_delta": primary_score - ward_score,
                       "basis": "same documents, Euclidean embeddings and selected k"},
    }


def run_clustering(config: dict) -> None:
    """Persist a complete snapshot; errors remain visible through job_manager."""
    sid = config.get("sid", "s0")
    job_manager.set("cluster", sid, {"status": "running", "phase": "loading", "progress": 0})
    try:
        input_key = _latest_key(f"classified/{sid}/", "relevant_", ".jsonl")
        if input_key is None:
            raise ValueError("No STEP 06 relevant snapshot; run classification first")
        result = _build_result(_load_records(input_key), sid, config)
        result["input_key"] = input_key
        # Reject NaN/Infinity anywhere, including copied metadata, before storage.
        json.dumps(result, allow_nan=False)
        key = f"clusters/{sid}/result_{result['timestamp']}.json"
        job_manager.update("cluster", sid, phase="saving", progress=95)
        s3.save_json(key, result)
        job_manager.set("cluster", sid, result_status(key, result))
    except Exception as exc:
        job_manager.update("cluster", sid, status="error", error=str(exc))


def refine_clusters(config: dict) -> dict:
    """Legacy keep/merge cannot preserve the new membership/metric contract.

    Reject it explicitly rather than drop Edge documents or publish stale bands
    and c-TF-IDF after merging. Use a fresh scored clustering run instead.
    """
    return {"status": "error", "error": "Legacy keep/merge is unsupported for STEP 07 snapshots; rerun /cluster with num_clusters"}
