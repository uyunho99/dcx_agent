"""Training selection shared by the worker and labeling overview."""
import numpy as np

TRAINING_WHERE = "source='human' OR (source='agreed' AND route='accepted')"


def training_rows(labels):
    with labels._db() as db:
        return [dict(row) for row in db.execute(
            f'SELECT * FROM final WHERE {TRAINING_WHERE} ORDER BY doc_id')]


def trainable_count(sid, data, labels):
    from app.model import infer
    from app.vectors.store import VectorStore
    if data.get('prep', {}).get('status') != 'done' or not data.get('prep', {}).get('derivedRef'):
        return 0
    with labels._db() as db:
        selected = {row[0] for row in db.execute(f'SELECT doc_id FROM final WHERE {TRAINING_WHERE}')}
    if not selected:
        return 0
    selected.intersection_update(infer.documents(sid, data))
    usable = set()
    for ids, matrix, _ in VectorStore(infer.prepared_root(sid, data)).iter_shards():
        mask = np.isfinite(matrix).all(axis=1) & np.any(matrix != 0, axis=1)
        usable.update(doc_id for doc_id, valid in zip(ids, mask) if valid and doc_id in selected)
    return len(usable)
