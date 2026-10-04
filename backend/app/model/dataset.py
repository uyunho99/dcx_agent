"""Training selection shared by the worker and labeling overview."""
import json

import numpy as np

TRAINING_WHERE = "source='human' OR (source IN ('agreed','gpt_only') AND route='accepted')"


def training_rows(labels):
    with labels._db() as db:
        return [dict(row) for row in db.execute(
            f'SELECT * FROM final WHERE {TRAINING_WHERE} ORDER BY doc_id')]


def _prepared_stamp(root):
    # Stat only: no document/index parsing or vector allocation on cache hits.
    paths = [root / 'manifest.json', root / 'docs', root / 'vectors/ids.jsonl',
             *sorted((root / 'docs').glob('*.jsonl')),
             *sorted((root / 'vectors').glob('shard-*.f16'))]
    stamps = []
    for path in paths:
        try:
            stat = path.stat()
            stamp = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)
        except FileNotFoundError:
            stamp = None
        stamps.append((str(path), stamp))
    return stamps


def _usable_schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS usable_docs (doc_id TEXT PRIMARY KEY)')
    db.execute('CREATE TABLE IF NOT EXISTS usable_meta (id INTEGER PRIMARY KEY CHECK(id=1), cache_key TEXT)')


def trainable_count(sid, data, labels):
    """Exact count of trainable labels with a usable vector.

    The expensive part (documents + vector validity) depends only on the prepared
    data, so it is cached per preparation stamp; label changes cost one SQL count.
    """
    from app.model import infer
    from app.vectors.store import VectorStore
    if data.get('prep', {}).get('status') != 'done' or not data.get('prep', {}).get('derivedRef'):
        return 0
    root = infer.prepared_root(sid, data)
    stamp = _prepared_stamp(root)
    key = json.dumps([2, data['prep']['derivedRef'], stamp], sort_keys=True)
    with labels._db() as db:
        _usable_schema(db)
        if not db.execute(f'SELECT 1 FROM final WHERE {TRAINING_WHERE} LIMIT 1').fetchone():
            return 0  # Nothing selectable yet: skip the document/vector scan entirely.
        row = db.execute('SELECT cache_key FROM usable_meta WHERE id=1').fetchone()
        fresh = row is not None and row['cache_key'] == key
    if not fresh:
        # Cold scan outside the labels write transaction (human submissions stay unblocked).
        documents = infer.documents(sid, data)
        usable = []
        for ids, matrix, _ in VectorStore(root).iter_shards():
            mask = np.isfinite(matrix).all(axis=1) & np.any(matrix != 0, axis=1)
            usable.extend(doc_id for doc_id, valid in zip(ids, mask) if valid and doc_id in documents)
        if _prepared_stamp(root) == stamp:
            with labels._db() as db:
                _usable_schema(db)
                db.execute('DELETE FROM usable_docs')
                db.executemany('INSERT OR IGNORE INTO usable_docs VALUES (?)', ((i,) for i in usable))
                db.execute('INSERT OR REPLACE INTO usable_meta VALUES (1, ?)', (key,))
        else:
            selected = set(usable)
            with labels._db() as db:
                return sum(1 for (doc_id,) in db.execute(f'SELECT doc_id FROM final WHERE {TRAINING_WHERE}')
                           if doc_id in selected)
    with labels._db() as db:
        return db.execute(f'SELECT count(*) FROM final WHERE ({TRAINING_WHERE}) '
                          'AND doc_id IN (SELECT doc_id FROM usable_docs)').fetchone()[0]
