"""Queue-only P5 reporting and lightweight live counters."""
from contextlib import closing
import time
from app.context import store
from app.crawl.gate import matrix
from app.crawl.queue import CrawlQueue


def channels(queue):
    return (store.read_json(queue.path.parent / 'worker_state.json') or {}).get('channels', {})


def progress(queue):
    with closing(CrawlQueue.open_readonly(queue.path)) as db:
        db.execute('BEGIN')
        counts = dict(db.execute('SELECT status,count(*) FROM urls GROUP BY status'))
        levels = dict(db.execute("SELECT fetch_level,count(*) FROM urls WHERE status='done' GROUP BY fetch_level"))
        restricted = db.execute("SELECT count(*) FROM urls WHERE status='done' AND access='restricted'").fetchone()[0]
        run = db.execute("SELECT * FROM runs WHERE kind='detail' ORDER BY started_at DESC LIMIT 1").fetchone()
        tasks = {r[0]: {'done': r[1], 'target': r[2]} for r in db.execute("SELECT source,sum(status='done'),count(*) FROM list_tasks GROUP BY source")}
    done = counts.get('done', 0)
    elapsed = max(1, ((run['heartbeat_at'] if run['status'] == 'done' else time.time()) - run['started_at'])) if run else 1
    return dict(done=done, target=sum(counts.values())-counts.get('filtered', 0)-counts.get('excluded', 0),
                full=levels.get('full', 0), snippet=levels.get('snippet', 0), restricted=restricted,
                per_minute=done * 60 / elapsed, channels=channels(queue), list_tasks=tasks)


def build_report(queue):
    cells = matrix(queue)
    p = progress(queue)
    with closing(CrawlQueue.open_readonly(queue.path)) as db:
        totals = dict(db.execute('SELECT status,count(*) FROM urls GROUP BY status'))
        totals['total'] = sum(totals.values())
        totals['doc_count'] = db.execute("SELECT coalesce(sum(doc_count),0) FROM urls WHERE status='done'").fetchone()[0]
        run = db.execute("SELECT * FROM runs WHERE kind='detail' ORDER BY started_at DESC LIMIT 1").fetchone()
        snap = db.execute('SELECT snapshot_id FROM snapshots ORDER BY created_at DESC LIMIT 1').fetchone()
        distribution = {}
        for source, docs in db.execute('SELECT source,sum(doc_count) FROM urls GROUP BY source'):
            errors = [{'error': r[0], 'count': r[1]} for r in db.execute('SELECT last_error,count(*) FROM urls WHERE source=? AND last_error IS NOT NULL GROUP BY last_error ORDER BY count(*) DESC LIMIT 5', (source,))]
            distribution[source] = dict(docs=docs, share=docs / totals['doc_count'] if totals['doc_count'] else 0,
                status=p['channels'].get(source, {}).get('status', 'idle'), errors_top=errors)
    state = store.read_json(queue.path.parent / 'worker_state.json') or {}
    return dict(matrix=cells, channels=distribution, totals=totals,
                counts={kw: {s: v['full'] + v['snippet'] for s, v in sources.items()} for kw, sources in cells.items()},
                snapshot_id=state.get('snapshot_id') or (snap[0] if snap else None),
                started_at=run['started_at'] if run else None, finished_at=run['heartbeat_at'] if run and run['status'] == 'done' else None,
                throughput_per_min=p['per_minute'])


def _write_report_locked(root):
    from app.crawl.control import latest_run, ReadQueue
    path = root / 'report.json'
    if path.exists():
        return store.read_json(path)
    queue = ReadQueue(root / 'queue.sqlite')
    run = latest_run(queue)
    if not run or run['kind'] != 'detail' or run['status'] != 'done':
        return None
    result = build_report(queue)
    store.write_json(path, result)
    for name in ('meta.json', 'manifest.json'):
        meta = store.read_json(root / name)
        if meta:
            store.write_json(root / name, {**meta, 'status': 'done'})
    return result


def write_report(sid):
    from app.crawl.control import collection_dir, collection_lock
    root = collection_dir(sid)
    with collection_lock(root):
        return _write_report_locked(root)
