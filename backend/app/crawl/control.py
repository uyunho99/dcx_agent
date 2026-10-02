"""Collection lifecycle and detached worker control.

Session mutations validate and write under the session store lock.
The collection lock serializes queue inspection and process launch. A 'starting'
run reserves the child PID without conflicting with the worker's register_run.
"""
from contextlib import closing, contextmanager
from copy import deepcopy
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
from app.work.proc import pid_alive
from app.context import store
from app.crawl.adapters import available_sources
from app.crawl.filters import DEFAULT_AD_WORDS, DEFAULT_EXCLUDE_SOURCES
from app.keywords.normalize import norm_key
from app.crawl.queue import CrawlQueue, KwMeta, STALE_AFTER_S
from app.crawl import gate, report


@dataclass
class ReadQueue:
    path: Path


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


def _mutate(sid, callback, version=None, confirm_stage=None):
    with store.locked(sid):
        session = store.assert_writable(sid, version)
        patch, result = callback(session)
        if patch:
            store._update_locked(sid, patch, confirm_stage=confirm_stage)
        return result


def _run_state(run):
    if not run:
        return 'idle'
    if run['status'] == 'done':
        return 'done'
    if (run['status'] in ('running', 'starting')
            and run['heartbeat_at'] >= time.time() - (30 if run['status'] == 'starting' else STALE_AFTER_S) and pid_alive(run['pid'])):
        return 'running'
    return 'interrupted'


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
    for row in rows:
        if _run_state(row) == 'running':
            return dict(row)
        # Fence before resetting state or signalling: save() uses the same SQLite
        # write lock, so an in-flight save finishes before this update commits.
        with closing(CrawlQueue(queue.path)) as writable:
            writable.connection.execute(
                "UPDATE runs SET status='interrupted' WHERE run_id=? AND status IN ('running','starting')",
                (row['run_id'],))
        if pid_alive(row['pid']):
            try:
                command = subprocess.run(['ps', '-p', str(row['pid']), '-o', 'args='],
                                         capture_output=True, text=True, timeout=2).stdout
                if 'app.crawl.worker' in command:
                    os.kill(row['pid'], signal.SIGTERM)
                    deadline = time.monotonic() + 5
                    while pid_alive(row['pid']):
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            break
                        time.sleep(min(.1, remaining))
            except (OSError, subprocess.SubprocessError):
                pass
    return None


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
            known.update(norm_key(k['kw']) for k in meta['keywords'])
            ancestor = meta['parent']
        keywords = []
        for kw in session.get('keywords', []):
            text = kw.get('kw', kw.get('text', ''))
            if kw.get('status') == 'approved' and text and norm_key(text) not in known:
                keywords.append(dict(kw, kw=text, crawlExcluded=False))
                known.add(norm_key(text))
        if not keywords:
            raise store.StoreError('No approved new keywords', 422, 'validation')
        cfg = session.get('crawlConfig', {})
        sources = cfg.get('channels', cfg.get('sources', [s for s in session.get('projectContext', {}).get('channels', []) if s in available_sources()]))
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
        config = dict(cfg, gateExclusions=[], filters=filters, channel_limits=cfg.get('perChannel', {}))
        store.write_json(root / 'manifest.json', dict(meta, channels=sources, config=config, snapshotId=None))
        with collection_lock(root), closing(CrawlQueue(root / 'queue.sqlite')) as queue:
            queue.add_list_tasks([KwMeta(k['kw'], k.get('axis', ''), k.get('sub', ''), i) for i,k in enumerate(keywords)], sources)
        return {'collectionId': root.name, 'step': 'crawl-list', 'crawlConfig': {'gateExclusions': []}, 'keywords': [dict(k, crawlExcluded=False) for k in session.get('keywords', [])]}, {'collectionId': root.name, 'version': session['version']}
    created = _mutate(sid, perform, version, confirm_stage='stage2')
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
                _gate_table(root, queue, session.get('crawlConfig', {}))
                queue.exclude_keywords(snapshot_id, session.get('crawlConfig', {}).get('gateExclusions', []))
                meta = store.read_json(root / 'manifest.json')
                store.write_json(root / 'manifest.json', dict(meta, snapshotId=snapshot_id, status='detail'))
                result = _spawn(sid, root, queue, 'detail', snapshot_id)
        return {'step': 'crawl-detail'}, result
    return _mutate(sid, perform, version)


def _unfinished_run(queue, run):
    if not run:
        return False
    # Completed lists await gate review unless legacy blocked failures remain.
    if run['kind'] == 'list':
        if run['status'] != 'done':
            return True
        with closing(CrawlQueue.open_readonly(queue.path)) as db:
            return db.execute("""SELECT 1 FROM list_tasks
                WHERE status='failed' AND last_error='AdapterBlocked' LIMIT 1""").fetchone() is not None
    return not report.can_finalize(queue, run)


def resume(sid, version=None, min_interval_s=None):
    def perform(session):
        root = collection_dir(sid)
        with collection_lock(root), closing(CrawlQueue(root / 'queue.sqlite')) as queue:
            run = latest_run(queue)
            if not _unfinished_run(queue, run):
                raise store.StoreError('No unfinished phase to resume')
            if not _live(queue):
                queue.reclaim_expired_leases()
            manifest = store.read_json(root / 'manifest.json')
            if not min_interval_s and not _live(queue):
                state = store.read_json(root / 'worker_state.json') or {}
                for channel in state.get('channels', {}).values():
                    if channel.get('status', '').startswith('paused'):
                        channel.update(status='running', attempts=0, blocked=0, parse_errors=0)
                state['paused_channels'] = []
                state.pop('stopReason', None)
                store.write_json(root / 'worker_state.json', state)
            if min_interval_s:
                if set(min_interval_s) - set(manifest['channels']):
                    raise store.StoreError('Unknown resume channel', 422, 'validation')
                if _live(queue):
                    raise store.StoreError('Worker is already running')
                config = manifest.setdefault('config', {})
                limits = config.setdefault('perChannel', deepcopy(config.get('channel_limits', {})))
                state = store.read_json(root / 'worker_state.json') or {}
                for source, interval in min_interval_s.items():
                    limits.setdefault(source, {})['min_interval_s'] = interval
                    state.get('channels', {}).get(source, {}).update(status='running', attempts=0, blocked=0, parse_errors=0)
                config['channel_limits'] = deepcopy(limits)
                state['paused_channels'] = [s for s, c in state.get('channels', {}).items() if c['status'].startswith('paused')]
                state.pop('stopReason', None)
                store.write_json(root / 'manifest.json', manifest)
                store.write_json(root / 'worker_state.json', state)
            if not _live(queue) and run['kind'] == 'list':
                queue.requeue_blocked_lists(min_interval_s or manifest['channels'])
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


def _gate_table(root, queue, cfg):
    """Caller holds collection lock; only P1 done/P3 not started may freeze."""
    path = root / 'gate.json'
    cached = store.read_json(path)
    # Preserve tables frozen by earlier versions, which stored a bare list.
    rows = cached if isinstance(cached, list) else cached.get('rows') if cached else None
    estimate_config = {k: cfg.get(k, default) for k, default in
                       [('gateExclusions', []), ('perChannel', {})]}
    if isinstance(cached, dict) and cached.get('estimateConfig') == estimate_config:
        return cached
    if rows is None:
        rows = [asdict(r) for r in gate.compute_gate(queue)]
    cached = dict(rows=rows, estimate=gate.estimate(queue, cfg), estimateConfig=estimate_config)
    store.write_json(path, cached)
    return cached


def _status_settings(session):
    keywords, known, visited = [], set(), set()
    ancestor = session.get('collectionId')
    base = Path(settings.local_data_dir).resolve() / 'crawl' / session['sid'] / 'collections'
    while ancestor:
        if ancestor in visited or not re.fullmatch(r'c[1-9][0-9]*', ancestor):
            raise store.StoreError('Invalid collection ancestry')
        visited.add(ancestor)
        meta = store.read_json(base / ancestor / 'meta.json')
        if not meta:
            raise store.StoreError('Parent collection not found', 404, 'not_found')
        for keyword in meta['keywords']:
            text = keyword['kw']
            key = norm_key(text)
            if key not in known:
                keywords.append(text)
                known.add(key)
        ancestor = meta.get('parent')
    added = {norm_key(k.get('kw', k.get('text', ''))) for k in session.get('keywords', [])
             if k.get('status') == 'approved'} - known - {''}
    channels, intervals = [], {}
    if session.get('collectionId'):
        manifest = store.read_json(base / session['collectionId'] / 'manifest.json')
        channels = manifest['channels']
        config = manifest.get('config', {})
        limits = config.get('perChannel', config.get('channel_limits', {}))
        # Match worker._Run's limiter precedence and default request spacing.
        intervals = {source: limits.get(source, {}).get(
            'min_interval_s', 0.5 if source in ('clien', 'ppomppu', 'naver_blog', 'naver_cafe') else 0)
            for source in channels}
    return dict(defaults=dict(adWords=DEFAULT_AD_WORDS.copy(), excludeSources=DEFAULT_EXCLUDE_SOURCES.copy()),
                available_sources=available_sources(), collection_keywords=keywords,
                collection_channels=channels, min_interval_s=intervals,
                added_keywords_count=len(added) if session.get('collectionId') else 0)


def status(sid):
    session = store.load_session(sid)
    if session is None:
        raise store.StoreError('Session not found', 404, 'not_found')
    settings_payload = _status_settings(session)
    if not session.get('collectionId'):
        return dict(**settings_payload, status='idle', resumable=False, kind=None, progress=None, gate=None, report=None, channels={}, updatedAt=session.get('updatedAt'))
    root = collection_dir(sid)
    queue = ReadQueue(root / 'queue.sqlite')
    run = latest_run(queue)
    state = _run_state(run)
    worker_state = store.read_json(root / 'worker_state.json') or {}
    p = report.progress(queue)
    with closing(CrawlQueue.open_readonly(queue.path)) as db:
        snapshot = db.execute('SELECT snapshot_id FROM snapshots ORDER BY created_at DESC LIMIT 1').fetchone()
    result = store.read_json(root / 'report.json')
    if run and run['kind'] == 'detail' and run['status'] == 'done' and result is None:
        with collection_lock(root):
            result = report._write_report_locked(root)
    table = store.read_json(root / 'gate.json')
    if snapshot and run and run['kind'] == 'list' and run['status'] == 'done':
        with collection_lock(root):
            table = _gate_table(root, queue, session.get('crawlConfig', {}))
    if run and run['status'] == 'done':
        step = 'crawl-done' if run['kind'] == 'detail' else 'crawl-gate'
        def sync_step(current):
            patch = {'step': step} if current.get('collectionId') == root.name and current.get('step') in ('crawl-list', 'crawl-detail', 'crawl-gate') and current.get('step') != step else {}
            return patch, {}
        if session.get('step') in ('crawl-list', 'crawl-detail', 'crawl-gate') and session.get('step') != step:
            try:
                _mutate(sid, sync_step, session.get('version'))
            except store.StoreError as exc:
                if exc.status != 409:
                    raise
    return dict(**settings_payload, status=state,
                resumable=state != 'running' and _unfinished_run(queue, run),
                remaining_by_channel=remaining_by_channel(queue),
                kind=run['kind'] if run else None, collectionId=root.name,
                progress=p, channels=p['channels'], paused_channels=worker_state.get('paused_channels', []),
                stopReason=worker_state.get('stopReason'), snapshot_id=snapshot[0] if snapshot else None,
                gate=table.get('rows') if isinstance(table, dict) else table,
                estimate=table.get('estimate') if isinstance(table, dict) else None,
                report=result, updatedAt=datetime.fromtimestamp(run['heartbeat_at'], timezone.utc).isoformat() if run else session.get('updatedAt'))


def activity(sid):
    kind = 'crawl_list'
    try:
        session = store.load_session(sid)
        if not session or not session.get('collectionId'):
            return None
        if session.get('step') in ('crawl-detail', 'crawl-done'):
            kind = 'crawl_detail'
        root = collection_dir(sid)
        queue = ReadQueue(root / 'queue.sqlite')
        if not queue.path.exists():
            return None
        run = latest_run(queue)
        state = _run_state(run)
        if state in ('idle', 'done'):
            return None
        kind = 'crawl_' + run['kind']
        return dict(kind=kind, status=state, progress=report.progress(queue),
                    updatedAt=datetime.fromtimestamp(run['heartbeat_at'], timezone.utc).isoformat())
    except Exception:
        # Activity is optional row metadata: damaged crawl files must not hide
        # unrelated sessions or prevent their version operations.
        return dict(kind=kind, status='unreadable', progress=None, updatedAt=None)


def save_gate(sid, exclusions, version=None):
    def perform(session):
        root = collection_dir(sid)
        with collection_lock(root):
            run = latest_run(ReadQueue(root / 'queue.sqlite'))
            if not run or run['kind'] != 'list' or run['status'] != 'done':
                raise store.StoreError('Gate is editable only after list completion')
            known = {norm_key(k['kw']): k['kw'] for k in store.read_json(root / 'meta.json')['keywords']}
            if {norm_key(k) for k in exclusions} - known.keys():
                raise store.StoreError('Unknown gate keyword', 422, 'validation')
            canonical = list(dict.fromkeys(known[norm_key(k)] for k in exclusions))
        keywords = [dict(k, crawlExcluded=norm_key(k.get('kw', k.get('text', ''))) in {norm_key(e) for e in canonical}) for k in session.get('keywords', [])]
        return {'crawlConfig': {'gateExclusions': canonical}, 'keywords': keywords, 'step': 'crawl-gate'}, {'status': 'ok', 'exclusions': canonical}
    return _mutate(sid, perform, version)


class _Replacement:
    """Use the store's deepcopy-on-nondict branch to replace a mapping."""
    def __init__(self, value):
        self.value = value

    def __deepcopy__(self, memo):
        return deepcopy(self.value, memo)


def save_config(sid, config, version=None):
    def perform(session):
        if set(config['channels']) - set(available_sources()):
            raise store.StoreError('Sources are unavailable', 422, 'validation')
        replacement = dict(config)
        current = session.get('crawlConfig', {})
        # Gate state is server-owned; replace only the user settings.
        if 'gateExclusions' in current:
            replacement['gateExclusions'] = current['gateExclusions']
        return {'crawlConfig': _Replacement(replacement)}, {'status': 'ok', 'crawlConfig': replacement}
    return _mutate(sid, perform, version)


def phase_state(sid, collection_id=None):
    """Read-only version guard; completed lists allow a fresh collection fork."""
    import sqlite3
    store.root_dir(sid)  # Validate even when an explicit collection is supplied.
    if collection_id is None:
        session = store.load_session(sid)
        collection_id = (session or {}).get('collectionId')
    if not collection_id:
        return 'none'
    if not re.fullmatch(r'c[1-9][0-9]*', collection_id):
        raise store.StoreError('No crawl collection', 409)
    try:
        root = Path(settings.local_data_dir).resolve() / 'crawl' / sid / 'collections' / collection_id
        queue = ReadQueue(root / 'queue.sqlite')
        run = latest_run(queue)
        if _run_state(run) == 'running':
            return 'running'
        if run and run['kind'] == 'list' and run['status'] == 'done':
            return 'gate'
        if report.can_finalize(queue, run):
            return 'done'
        return 'unfinished'
    except (OSError, sqlite3.Error):
        return 'unfinished'


def remaining_by_channel(queue):
    manifest = store.read_json(queue.path.parent / 'manifest.json') or {}
    snapshot = manifest.get('snapshotId')
    with closing(CrawlQueue.open_readonly(queue.path)) as db:
        return dict(db.execute('''SELECT source,count(*) FROM urls
            WHERE status IN ('pending','leased') AND (? IS NULL OR EXISTS
              (SELECT 1 FROM snapshot_urls s WHERE s.snapshot_id=?
               AND s.url_norm=urls.url_norm AND s.source=urls.source)) GROUP BY source''',
            (snapshot, snapshot)))


def finish_partial(sid, version=None):
    """D-097: blocked and parse-error pauses may explicitly skip remaining URLs."""
    def perform(session):
        root = collection_dir(sid)
        with collection_lock(root), closing(CrawlQueue(root / 'queue.sqlite')) as queue:
            if _live(queue):
                raise store.StoreError('Worker is already running')
            run = latest_run(queue)
            state = store.read_json(root / 'worker_state.json') or {}
            paused = {s: c['status'].removeprefix('paused_')
                      for s, c in state.get('channels', {}).items()
                      if c.get('status') in ('paused_blocked', 'paused_parse_error')}
            if not run or run['kind'] != 'detail' or not paused or not _unfinished_run(queue, run):
                raise store.StoreError('No paused detail channels')
            remaining = remaining_by_channel(queue)
            if any(count and source not in paused for source, count in remaining.items()):
                raise store.StoreError('Other channels are unfinished')
            snapshot = (store.read_json(root / 'manifest.json') or {}).get('snapshotId')
            # Fence and skip in one transaction; a stale worker cannot save later.
            with queue._write() as db:
                for source, reason in paused.items():
                    db.execute('''UPDATE urls SET status='skipped',last_error=?,
                        lease_until=NULL,lease_run_id=NULL,lease_snapshot_id=NULL,retry_at=NULL
                        WHERE source=? AND status IN ('pending','leased') AND (? IS NULL OR EXISTS
                          (SELECT 1 FROM snapshot_urls s WHERE s.snapshot_id=?
                           AND s.url_norm=urls.url_norm AND s.source=urls.source))''',
                        (reason, source, snapshot, snapshot))
                db.execute("UPDATE runs SET status='done',heartbeat_at=? WHERE run_id=?", (time.time(), run['run_id']))
            for source in paused:
                state['channels'][source]['status'] = 'done'
            state.update(paused_channels=[], stopReason='partial_finished')
            store.write_json(root / 'worker_state.json', state)
            result = report._write_report_locked(root)
        return {'step': 'crawl-done'}, {'status': 'done', 'report': result}
    return _mutate(sid, perform, version)
