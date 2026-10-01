"""Training selection shared by the worker and labeling overview."""
import json

import numpy as np

TRAINING_WHERE = "source='human' OR (source='agreed' AND route='accepted')"


def training_rows(labels):
    with labels._db() as db:
        return [dict(row) for row in db.execute(
            f'SELECT * FROM final WHERE {TRAINING_WHERE} ORDER BY doc_id')]


def _count_schema(db):
    # A durable counter works across short-lived connections and processes;
    # max(rowid) misses in-place updates/deletes, and data_version is connection-local.
    db.execute('''CREATE TABLE IF NOT EXISTS trainable_cache (
        id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL,
        cache_key TEXT, count INTEGER)''')
    db.execute('INSERT OR IGNORE INTO trainable_cache(id, revision) VALUES (1, 0)')
    for table in ('final', 'human'):
        for action in ('INSERT', 'UPDATE', 'DELETE'):
            db.execute(f'''CREATE TRIGGER IF NOT EXISTS trainable_{table}_{action.lower()}
                AFTER {action} ON {table} BEGIN
                UPDATE trainable_cache SET revision=revision+1 WHERE id=1; END''')


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


def trainable_count(sid, data, labels):
    """Persist the exact selection count until prepared data or labels change."""
    from app.model import infer
    from app.vectors.store import VectorStore
    if data.get('prep', {}).get('status') != 'done' or not data.get('prep', {}).get('derivedRef'):
        return 0
    root = infer.prepared_root(sid, data)
    stamp = _prepared_stamp(root)
    with labels._db() as db:
        _count_schema(db)
        cached = db.execute('SELECT * FROM trainable_cache WHERE id=1').fetchone()
        revision = cached['revision']
        key = json.dumps([1, TRAINING_WHERE, data['prep']['derivedRef'], stamp, revision], sort_keys=True)
        if cached['cache_key'] == key:
            return cached['count']
        selected = {row[0] for row in db.execute(f'SELECT doc_id FROM final WHERE {TRAINING_WHERE}')}
    # Do the cold scan outside the labels write transaction so human submissions
    # are not blocked by document parsing and vector loading.
    usable = set()
    if selected:
        selected.intersection_update(infer.documents(sid, data))
        for ids, matrix, _ in VectorStore(root).iter_shards():
            mask = np.isfinite(matrix).all(axis=1) & np.any(matrix != 0, axis=1)
            usable.update(doc_id for doc_id, valid in zip(ids, mask) if valid and doc_id in selected)
    if _prepared_stamp(root) == stamp:
        with labels._db() as db:
            # Never publish a scan as current if a label changed while it ran.
            db.execute('UPDATE trainable_cache SET cache_key=?, count=? WHERE id=1 AND revision=?',
                       (key, len(usable), revision))
    return len(usable)
