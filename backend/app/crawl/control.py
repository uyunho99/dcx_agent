"""Collection lifecycle and detached worker control.

Session mutations use update_session's locked merge callback, like keyword jobs.
The collection lock serializes queue inspection and process launch. A 'starting'
run reserves the child PID without conflicting with the worker's register_run.
"""
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from uuid import uuid4

from app.config import settings
from app.context import store
from app.crawl.adapters import available_sources
from app.crawl.queue import CrawlQueue, KwMeta
from app.crawl import gate, report


@dataclass
class ReadQueue:
    path: Path


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def collection_dir(sid):
    session = store.load_session(sid)
    if session is None:
        raise store.StoreError('Session not found', 404, 'not_found')
    cid = session.get('collectionId')
    if not cid or not re.fullmatch(r'c[1-9][0-9]*', cid):
        raise store.StoreError('No crawl collection', 409)
    return Path(settings.local_data_dir).resolve() / 'crawl' / sid / 'collections' / cid


@contextmanager
def collection_lock(root):
    with (root / '.control.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


class _CheckedPatch(dict):
    def __init__(self, callback):
        self.callback = callback

    def items(self):
        self.update(self.callback())
        return super().items()


def _mutate(sid, callback, version=None):
    result = {}
    def checked():
        session = store.assert_writable(sid, version)
        patch, value = callback(session)
        result.update(value)
        return patch
    store.update_session(sid, _CheckedPatch(checked))
    return result


def latest_run(queue):
    with closing(CrawlQueue.open_readonly(queue.path)) as db:
        # A reservation is superseded once its child registers an actual run.
        row = db.execute('''SELECT * FROM runs r WHERE status!='starting' OR NOT EXISTS
            (SELECT 1 FROM runs w WHERE w.pid=r.pid AND w.kind=r.kind AND w.status!='starting'
             AND w.started_at>=r.started_at)
            ORDER BY started_at DESC LIMIT 1''').fetchone()
        return dict(row) if row else None


def _live(queue):
    with closing(CrawlQueue.open_readonly(queue.path)) as db:
        rows = db.execute('''SELECT * FROM runs r WHERE status IN ('running','starting')
            AND (status!='starting' OR NOT EXISTS(SELECT 1 FROM runs w WHERE w.pid=r.pid
                AND w.kind=r.kind AND w.status!='starting' AND w.started_at>=r.started_at))''').fetchall()
    return next((dict(r) for r in rows if pid_alive(r['pid'])), None)


def _spawn(sid, root, queue, kind, snapshot=None):
    live = _live(queue)
    if live:
        if live['kind'] != kind:
            raise store.StoreError('Another crawl phase is running')
        return dict(collectionId=root.name, kind=kind, status='running', pid=live['pid'])
    if (root / 'report.json').exists():
        raise store.StoreError('Finished collections are immutable')
    args = [sys.executable, '-m', 'app.crawl.worker', kind, '--sid', sid, '--collection', str(root)]
    if snapshot:
        args += ['--snapshot', snapshot]
    # Holding a SQLite write transaction prevents a fast child registering before
    # its reservation is committed. The child only rejects status='running'.
    queue.connection.execute('BEGIN IMMEDIATE')
    try:
        with (root / f'{kind}.log').open('ab') as log:
            child = subprocess.Popen(args, cwd=str(Path(__file__).resolve().parents[2]),
                                     start_new_session=True, stdout=log, stderr=log)
        now = time.time()
        queue.connection.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)',
            (uuid4().hex, str(root), kind, child.pid, 'starting', now, now, '{}'))
        queue.connection.commit()
    except BaseException:
        queue.connection.rollback()
        raise
    return dict(collectionId=root.name, kind=kind, status='running', pid=child.pid)


def start_list(sid, mode=None, version=None):
    if mode not in (None, 'added-keywords'):
        raise store.StoreError('Invalid list mode', 422, 'validation')
    def perform(session):
        if session.get('collectionId'):
            previous = collection_dir(sid)
            with collection_lock(previous):
                if _live(ReadQueue(previous / 'queue.sqlite')):
                    raise store.StoreError('A crawl worker is running')
                report._write_report_locked(previous)
        base = Path(settings.local_data_dir).resolve() / 'crawl' / sid / 'collections'
        base.mkdir(parents=True, exist_ok=True)
        parent = session.get('collectionId') if mode == 'added-keywords' else None
        if mode == 'added-keywords' and not parent:
            raise store.StoreError('Added-keywords mode requires a parent collection')
        known, visited = set(), set()
        ancestor = parent
        while ancestor:
            if ancestor in visited or not re.fullmatch(r'c[1-9][0-9]*', ancestor):
                raise store.StoreError('Invalid collection ancestry')
            visited.add(ancestor)
            meta = store.read_json(base / ancestor / 'meta.json')
            if not meta:
                raise store.StoreError('Parent collection not found', 404, 'not_found')
            known.update(k['kw'] for k in meta['keywords'])
            ancestor = meta['parent']
        keywords = []
        for kw in session.get('keywords', []):
            text = kw.get('kw', kw.get('text', ''))
            if kw.get('status') == 'approved' and text and text not in known:
                keywords.append(dict(kw, kw=text))
                known.add(text)
        if not keywords:
            raise store.StoreError('No approved new keywords', 422, 'validation')
        cfg = session.get('crawlConfig', {})
        sources = cfg.get('channels', cfg.get('sources', available_sources()))
        if not sources or set(sources) - set(available_sources()):
            raise store.StoreError('Sources are unavailable', 422, 'validation')
        number = max([int(p.name[1:]) for p in base.iterdir() if re.fullmatch(r'c[1-9][0-9]*', p.name)] or [0]) + 1
        root = base / f'c{number}'
        root.mkdir()
        meta = dict(id=root.name, parent=parent, createdAt=store.now(), keywords=keywords, status='list')
        store.write_json(root / 'meta.json', meta)
        filters = {}
        for source, target in [('dateFrom','date_from'), ('dateTo','date_to'), ('adWords','ad_words'),
                               ('excludeSources','exclude_sources'), ('includeSources','include_sources'),
                               ('productNameFilter','product_name_filter'), ('product_name_filter','product_name_filter')]:
            if source in cfg:
                filters[target] = cfg[source]
        filters['bk'] = session.get('projectContext', {}).get('bk', '')
        config = dict(cfg, filters=filters, channel_limits=cfg.get('perChannel', {}))
        store.write_json(root / 'manifest.json', dict(meta, channels=sources, config=config, snapshotId=None))
        with collection_lock(root), closing(CrawlQueue(root / 'queue.sqlite')) as queue:
            queue.add_list_tasks([KwMeta(k['kw'], k.get('axis', ''), k.get('sub', ''), i) for i,k in enumerate(keywords)], sources)
        return {'collectionId': root.name, 'step': 'crawl-list', 'crawlConfig': {'gateExclusions': []}}, {'collectionId': root.name, 'version': session['version']}
    created = _mutate(sid, perform, version)
    # Persist collectionId before launch so both the worker and session readers
    # observe the new collection. Revalidate after reacquiring the session lock.
    def launch(session):
        if session.get('collectionId') != created['collectionId']:
            raise store.StoreError('Active collection changed before launch')
        root = collection_dir(sid)
        with collection_lock(root), closing(CrawlQueue(root / 'queue.sqlite')) as queue:
            result = _spawn(sid, root, queue, 'list')
        return {}, result
    return _mutate(sid, launch, created['version'])


def start_detail(sid, snapshot_id, version=None):
    def perform(session):
        root = collection_dir(sid)
        with collection_lock(root), closing(CrawlQueue(root / 'queue.sqlite')) as queue:
            run = latest_run(queue)
            if not run or (run['kind'] == 'list' and run['status'] != 'done'):
                raise store.StoreError('Finish list collection before starting detail')
            if not queue.connection.execute('SELECT 1 FROM snapshots WHERE snapshot_id=?', (snapshot_id,)).fetchone():
                raise store.StoreError('Snapshot not found', 404, 'not_found')
            live = _live(queue)
            if live:
                manifest = store.read_json(root / 'manifest.json')
                if manifest.get('snapshotId') != snapshot_id:
                    raise store.StoreError('Detail snapshot is already selected')
                result = _spawn(sid, root, queue, 'detail', snapshot_id)
            else:
                if run['kind'] == 'detail' and run['status'] == 'done':
                    raise store.StoreError('Finished collections are immutable')
                if run['kind'] == 'detail':
                    raise store.StoreError('Resume the unfinished detail phase')
                _gate_table(root, queue)
                queue.exclude_keywords(snapshot_id, session.get('crawlConfig', {}).get('gateExclusions', []))
                meta = store.read_json(root / 'manifest.json')
                store.write_json(root / 'manifest.json', dict(meta, snapshotId=snapshot_id, status='detail'))
                result = _spawn(sid, root, queue, 'detail', snapshot_id)
        return {'step': 'crawl-detail'}, result
    return _mutate(sid, perform, version)


def resume(sid, version=None):
    def perform(session):
        root = collection_dir(sid)
        with collection_lock(root), closing(CrawlQueue(root / 'queue.sqlite')) as queue:
            run = latest_run(queue)
            if not run or run['status'] == 'done':
                raise store.StoreError('No unfinished phase to resume')
            if not _live(queue):
                queue.reclaim_expired_leases()
            manifest = store.read_json(root / 'manifest.json')
            result = _spawn(sid, root, queue, run['kind'], manifest.get('snapshotId'))
        return {'step': 'crawl-' + run['kind']}, result
    return _mutate(sid, perform, version)


def stop(sid, version=None):
    def perform(session):
        root = collection_dir(sid)
        with collection_lock(root):
            live = _live(ReadQueue(root / 'queue.sqlite'))
            if live:
                try:
                    os.kill(live['pid'], signal.SIGTERM)
                except ProcessLookupError:
                    pass
        return {}, {'status': 'stopping' if live else 'idle', 'collectionId': root.name}
    return _mutate(sid, perform, version)


def _gate_table(root, queue):
    """Caller holds collection lock. Freeze P1 aggregates before P3 changes URLs."""
    path = root / 'gate.json'
    if path.exists():
        return store.read_json(path)
    rows = [asdict(r) for r in gate.compute_gate(queue)]
    store.write_json(path, rows)
    return rows


def status(sid):
    session = store.load_session(sid)
    if session is None:
        raise store.StoreError('Session not found', 404, 'not_found')
    if not session.get('collectionId'):
        return dict(status='idle', kind=None, progress=None, gate=None, report=None, channels={}, updatedAt=session.get('updatedAt'))
    root = collection_dir(sid)
    queue = ReadQueue(root / 'queue.sqlite')
    run = latest_run(queue)
    state = 'idle'
    if run:
        if run['status'] == 'done':
            state = 'done'
        elif pid_alive(run['pid']) and run['status'] in ('running', 'starting'):
            state = 'running' if run['heartbeat_at'] >= time.time() - 60 else 'interrupted'
        else:
            state = 'interrupted'
    p = report.progress(queue)
    with closing(CrawlQueue.open_readonly(queue.path)) as db:
        snapshot = db.execute('SELECT snapshot_id FROM snapshots ORDER BY created_at DESC LIMIT 1').fetchone()
    result = store.read_json(root / 'report.json')
    if run and run['kind'] == 'detail' and run['status'] == 'done' and result is None:
        with collection_lock(root):
            result = report._write_report_locked(root)
    table = store.read_json(root / 'gate.json')
    if table is None and snapshot and run and run['kind'] == 'list' and run['status'] == 'done':
        with collection_lock(root):
            table = _gate_table(root, queue)
    if run and run['status'] == 'done':
        step = 'crawl-done' if run['kind'] == 'detail' else 'crawl-gate'
        def sync_step(current):
            patch = {'step': step} if current.get('collectionId') == root.name and current.get('step') in ('crawl-list', 'crawl-detail', 'crawl-gate') else {}
            return patch, {}
        if session.get('step') != step:
            try:
                _mutate(sid, sync_step, session.get('version'))
            except store.StoreError as exc:
                if exc.status != 409:
                    raise
    return dict(status=state, kind=run['kind'] if run else None, collectionId=root.name,
                progress=p, channels=p['channels'], snapshot_id=snapshot[0] if snapshot else None,
                gate=table,
                estimate=gate.estimate(queue, session.get('crawlConfig', {})) if snapshot else None,
                report=result, updatedAt=datetime.fromtimestamp(run['heartbeat_at'], timezone.utc).isoformat() if run else session.get('updatedAt'))


def activity(sid):
    session = store.load_session(sid)
    if not session or not session.get('collectionId'):
        return None
    root = collection_dir(sid)
    queue = ReadQueue(root / 'queue.sqlite')
    if not queue.path.exists():
        return None
    run = latest_run(queue)
    if not run:
        return None
    state = 'done' if run['status'] == 'done' else 'running' if run['status'] in ('running', 'starting') and pid_alive(run['pid']) else 'interrupted'
    return dict(kind='crawl_' + run['kind'], status=state, progress=report.progress(queue),
                updatedAt=datetime.fromtimestamp(run['heartbeat_at'], timezone.utc).isoformat())


def save_gate(sid, exclusions, version=None):
    def perform(session):
        root = collection_dir(sid)
        with collection_lock(root):
            run = latest_run(ReadQueue(root / 'queue.sqlite'))
            if not run or run['kind'] != 'list' or run['status'] != 'done':
                raise store.StoreError('Gate is editable only after list completion')
            known = {k['kw'] for k in store.read_json(root / 'meta.json')['keywords']}
            if set(exclusions) - known:
                raise store.StoreError('Unknown gate keyword', 422, 'validation')
        keywords = [dict(k, crawlExcluded=k.get('kw', k.get('text')) in exclusions) for k in session.get('keywords', [])]
        return {'crawlConfig': {'gateExclusions': exclusions}, 'keywords': keywords, 'step': 'crawl-gate'}, {'status': 'ok', 'exclusions': exclusions}
    return _mutate(sid, perform, version)


def save_config(sid, config, version=None):
    def perform(session):
        if set(config['channels']) - set(available_sources()):
            raise store.StoreError('Sources are unavailable', 422, 'validation')
        return {'crawlConfig': config}, {'status': 'ok', 'crawlConfig': dict(session.get('crawlConfig', {}), **config)}
    return _mutate(sid, perform, version)
