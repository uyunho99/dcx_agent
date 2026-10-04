"""P1/P3 processes; only the coordinator thread accesses SQLite or P4 files.

DCX_TEST_ADAPTER_MODULE optionally imports a local registration module. It is
inert by default and intended solely for subprocess tests with fake adapters.
"""
import argparse
from collections import deque
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import ExitStack, contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import importlib
import inspect
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time

from app.config import settings
from app.crawl.errors import safe_error
from app.context.store import load_session, read_json, write_json
from app.crawl.adapters import REGISTRY, available_sources, managed_adapter
from app.crawl.adapters.naver_common import NaverAdapter
from app.crawl.adapters.community import DEFAULT_INTERVAL_S
from app.crawl.adapters.base import AdapterBlocked, FetchedDoc, ListItem, ListPage
from app.crawl.filters import FilterConfig, check_doc, check_list
from app.crawl.hashing import author_hash
from app.crawl.queue import CrawlQueue, HEARTBEAT_INTERVAL, KwMeta, LeaseLost
from app.crawl.ratelimit import ChannelLimiter
from app.crawl.schema import Doc
from app.crawl.urls import doc_id, normalize_url
from app.crawl.writer import DocWriter
from app.utils.text import clean_text

BATCH_SIZE = 200
FETCH_TIMEOUT_S = 60
# Heartbeats fence dead owners; a long lease avoids expiring a healthy slow fetch.
LEASE_SECONDS = 86400


class AdapterParseError(ValueError):
    """Adapters may use this (or ValueError/TypeError) for malformed responses."""


def _load_hook():
    module = os.environ.get('DCX_TEST_ADAPTER_MODULE')
    if module:
        importlib.import_module(module)


def _inputs(sid, collection):
    if collection is not None:
        root = Path(collection)
        session = {}
    else:
        session = load_session(sid) or {}
        cid = session.get('collectionId')
        if not cid:
            raise ValueError(f'Session {sid} has no collectionId; create a collection first')
        if Path(cid).name != cid or cid in ('.', '..'):
            raise ValueError('Invalid collectionId')
        root = Path(settings.local_data_dir) / 'crawl' / sid / 'collections' / cid
    root.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((root / 'manifest.json').read_text()) if (root / 'manifest.json').exists() else {}
    config = manifest.get('config', session.get('crawlConfig', {}))
    return root, session, manifest, config


def _keywords(values):
    result = []
    for i, value in enumerate(values):
        if isinstance(value, KwMeta):
            result.append(value)
        elif isinstance(value, str):
            result.append(KwMeta(value, '', '', i))
        else:
            result.append(KwMeta(value.get('text', value.get('kw', '')), value.get('axis', ''),
                                 value.get('sub', ''), i))
    return result


@contextmanager
def _stop_event():
    event = threading.Event()
    previous = None
    if threading.current_thread() is threading.main_thread():
        previous = signal.signal(signal.SIGTERM, lambda *_: event.set())
    try:
        yield event
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)


class _Run:
    def __init__(self, root, sid, kind, sources, limiters, config, snapshot=None):
        self.root, self.sid, self.kind, self.snapshot = root, sid, kind, snapshot
        self.q = CrawlQueue(root / 'queue.sqlite')
        try:
            self.id = self.q.register_run(kind)
        except BaseException:
            self.q.close()
            raise
        previous = read_json(root / 'worker_state.json') or {}
        self.channels = {s: dict(status='running', attempts=0, parse_errors=0, blocked=0) for s in sources}
        if previous.get('kind') == kind:
            for source, channel in previous.get('channels', {}).items():
                if source in self.channels and channel.get('status', '').startswith('paused'):
                    self.channels[source] = channel
        self.config = config
        self.stop_reason = None
        self.target_total = config.get('target_total') or 0
        self.completed_docs = self.q.counts()['doc_count'] if kind == 'detail' else 0
        self.limiters = {}
        for s in sources:
            defaults = (2, 0) if s == 'youtube' else ((1, 0.5) if s in ('clien', 'ppomppu', 'naver_blog', 'naver_cafe') else (4, 0))
            opts = config.get('perChannel', config.get('channel_limits', {})).get(s, {})
            self.limiters[s] = (limiters or {}).get(s) or ChannelLimiter(
                opts.get('concurrency', defaults[0]), opts.get('min_interval_s', defaults[1]))
        self.pools = {s: ThreadPoolExecutor(max_workers=l.concurrency) for s, l in self.limiters.items()}
        self.last_heartbeat = self.last_reclaim = time.monotonic()
        self.save()

    def share_naver_search_limiter(self, adapters):
        naver = {s: a for s, a in adapters.items()
                 if s in ('naver_blog', 'naver_cafe') and isinstance(a, NaverAdapter)}
        if naver:
            limiter = ChannelLimiter(1, max(
                DEFAULT_INTERVAL_S, *(self.limiters[s].min_interval_s for s in naver)))
            limiter.blocked = False
            for adapter in naver.values():
                adapter.search_limiter = limiter

    def save(self):
        # Serialize ownership validation and the atomic file replacement with
        # run fencing/registration, including the interval before respawn.
        with self.q._write() as db:
            latest = db.execute('SELECT run_id,status FROM runs ORDER BY started_at DESC, rowid DESC LIMIT 1').fetchone()
            if not latest or latest['run_id'] != self.id or latest['status'] != 'running':
                return
            write_json(self.root / 'worker_state.json', dict(sid=self.sid, kind=self.kind,
                       run_id=self.id, snapshot_id=self.snapshot, channels=self.channels,
                       paused_channels=[s for s, c in self.channels.items() if c['status'].startswith('paused')],
                       **({'stopReason': self.stop_reason} if self.stop_reason else {})))

    def target_reached(self):
        if self.target_total > 0 and self.completed_docs >= self.target_total:
            self.stop_reason = 'target_reached'
            return True
        return False

    def list_remaining(self, task):
        opts = self.config.get('perChannel', self.config.get('channel_limits', {}))
        caps = [opts.get(task.source, {}).get('max_per_keyword') or 0]
        if task.source == 'youtube':
            caps.append(self.config.get('youtube', {}).get('videos_per_keyword') or 0)
        caps = [cap for cap in caps if cap > 0]
        if not caps:
            return None
        listed = self.q.connection.execute(
            'SELECT coalesce(sum(fetched),0) FROM list_tasks WHERE kw=? AND source=?',
            (task.kw, task.source)).fetchone()[0]
        return max(0, min(caps) - listed)

    def tick(self):
        now = time.monotonic()
        if now - self.last_heartbeat >= HEARTBEAT_INTERVAL:
            self.q.heartbeat(self.id)
            self.last_heartbeat = now
        if now - self.last_reclaim >= 60:
            self.q.reclaim_expired_leases()
            self.last_reclaim = now

    def active(self, source):
        return self.channels[source]['status'] == 'running'

    def outcome(self, source, error):
        c = self.channels[source]
        c['attempts'] += 1
        c['blocked'] = c['blocked'] + 1 if isinstance(error, AdapterBlocked) else 0
        c['parse_errors'] += isinstance(error, (ValueError, TypeError, KeyError, AttributeError, IndexError))
        if isinstance(error, AdapterBlocked) and error.host == 'search.naver.com':
            for s in ('naver_blog', 'naver_cafe'):
                if s in self.channels:
                    self.channels[s]['status'] = 'paused_blocked'
        elif c['blocked'] >= 20:
            c['status'] = 'paused_blocked'
        elif c['attempts'] >= 10 and c['parse_errors'] / c['attempts'] > 0.3:
            c['status'] = 'paused_parse_error'
        self.save()

    def execute(self, jobs, adapters, method, stop):
        """Route a bounded wave to per-channel pools; never queue a paused channel."""
        pending = {s: deque() for s in self.channels}
        for job in jobs:
            pending[job.source].append(job)
        futures = {}
        running = dict.fromkeys(self.channels, 0)
        def call(source, job):
            with self.limiters[source]:
                adapter = adapters[source]
                if method == 'list':
                    options = {}
                    limit = self.config.get('youtube', {}).get('videos_per_keyword', 20)
                    if source == 'youtube' and limit > 0:
                        try:
                            inspect.signature(adapter.list_page).bind(job.kw, job.cursor, videos_per_keyword=limit)
                        except (TypeError, ValueError):
                            pass  # Preserve injected legacy adapter contracts.
                        else:
                            options['videos_per_keyword'] = limit
                    page = adapter.list_page(job.kw, job.cursor, **options)
                    if not isinstance(page, ListPage) or any(not isinstance(i, ListItem) for i in page.items):
                        raise AdapterParseError('Expected ListPage containing ListItem records')
                    return page
                docs = adapter.fetch(ListItem(job.url_norm, job.title, job.snippet, job.date, job.src_meta))
                if not isinstance(docs, list) or any(not isinstance(d, FetchedDoc) for d in docs):
                    raise AdapterParseError('Expected a list of FetchedDoc records')
                return docs
        while futures or any(pending.values()):
            self.tick()
            for s, rows in pending.items():
                if not self.active(s) or stop.is_set():
                    rows.clear()
                while rows and running[s] < self.limiters[s].concurrency:
                    job = rows.popleft()
                    if method == 'detail' and job.exhausted:
                        yield job, None, None
                        continue
                    f = self.pools[s].submit(call, s, job)
                    futures[f] = job
                    running[s] += 1
            if not futures:
                continue
            done, _ = wait(futures, timeout=0.1, return_when=FIRST_COMPLETED)
            for f in done:
                job = futures.pop(f)
                running[job.source] -= 1
                try:
                    result, error = f.result(), None
                except Exception as exc:
                    result, error = None, exc
                self.outcome(job.source, error)
                yield job, result, error

    def close(self, status):
        if status == 'done' and self.stop_reason != 'target_reached':
            if self.kind == 'list':
                pending = self.q.connection.execute(
                    "SELECT 1 FROM list_tasks WHERE status IN ('pending','running','leased') LIMIT 1").fetchone()
            else:
                pending = self.q.connection.execute(
                    "SELECT 1 FROM urls JOIN snapshot_urls USING(url_norm,source) "
                    "WHERE snapshot_id=? AND status IN ('pending','leased') LIMIT 1",
                    (self.snapshot,)).fetchone()
            if pending:
                status = 'paused'
                self.stop_reason = 'pending_channels'
        try:
            for c in self.channels.values():
                if c['status'] == 'running':
                    c['status'] = status
            self.save()
            self.q.finish_run(self.id, status)
        finally:
            for pool in self.pools.values():
                pool.shutdown(wait=False, cancel_futures=True)
            self.q.close()


def _error(exc):
    return safe_error(exc)


def run_list(sid, *, collection=None, keywords=None, sources=None, filters=None, limiters=None):
    _load_hook()
    root, session, manifest, config = _inputs(sid, collection)
    kws = _keywords(keywords if keywords is not None else manifest.get('keywords', session.get('keywords', [])))
    if sources is None:
        sources = manifest.get('channels', config.get('channels'))
    if sources is None:
        sources = available_sources()
    sources = list(dict.fromkeys(sources))
    filters = filters or FilterConfig(**config.get('filters', {}))
    resources = ExitStack()
    run = None
    status = 'interrupted'
    try:
        adapters = {s: resources.enter_context(managed_adapter(REGISTRY[s])) for s in sources}
        run = _Run(root, sid, 'list', sources, limiters, config)
        run.share_naver_search_limiter(adapters)
        run.q.add_list_tasks(kws, sources)
        with _stop_event() as stop:
            while not stop.is_set():
                jobs = [task for s in sources if run.active(s)
                        for task in run.q.next_list_tasks(s, run.limiters[s].concurrency)]
                if not jobs:
                    break
                dispatch = []
                for task in jobs:
                    if run.list_remaining(task) == 0:
                        run.q.record_list_page(task, [], None)
                    else:
                        dispatch.append(task)
                for task, page, error in run.execute(dispatch, adapters, 'list', stop):
                    if error:
                        run.q.mark_list_failed(task, _error(error), blocked=isinstance(error, AdapterBlocked))
                        continue
                    remaining = run.list_remaining(task)
                    items = page.items if remaining is None else page.items[:remaining]
                    cursor = None if remaining is not None and len(items) >= remaining else page.next_cursor
                    rules = [check_list(dict(asdict(item), source=task.source), filters) for item in items]
                    run.q.record_list_page(task, items, cursor, filter_rules=rules)
            run.snapshot = run.q.take_snapshot()
            status = 'stopped' if stop.is_set() else 'done'
            if not stop.is_set():
                for row in run.q.connection.execute("SELECT DISTINCT source FROM list_tasks WHERE status='failed'"):
                    if row['source'] in run.channels and run.active(row['source']):
                        run.channels[row['source']]['status'] = 'failed'
            return run.snapshot
    finally:
        try:
            if run is not None:
                run.close(status)
        finally:
            resources.close()


def _clean(text):
    return ' '.join(clean_text(text).split())


def _doc(row, fetched, level):
    return Doc(doc_id=doc_id(row.source, row.url_norm, fetched.thread_key), source=row.source,
        src_meta=fetched.src_meta, kw=row.kw, kw_axis=row.kw_axis, kw_sub=row.kw_sub,
        kw_hits=row.kw_hits, title=_clean(fetched.title), body=_clean(fetched.body),
        comments=[c.model_copy(update={'text': _clean(c.text)}) for c in fetched.comments],
        date=fetched.date or '', url=row.url_norm, fetch_level=level, access=fetched.access,
        snippet=_clean(row.snippet), author_hash=author_hash(row.source, fetched.author_raw) if fetched.author_raw else '',
        crawled_at=datetime.now(timezone.utc).isoformat())


def _remaining(run):
    # Read-only SQL narrows pending work to this snapshot and unpaused sources.
    # Mutations exclusively use CrawlQueue's public API.
    sources = [s for s in run.channels if run.active(s)]
    if not sources:
        return False
    marks = ','.join('?' for _ in sources)
    return run.q.connection.execute(f'''SELECT 1 FROM urls u JOIN snapshot_urls s USING(url_norm,source)
        WHERE s.snapshot_id=? AND u.status='pending' AND u.source IN ({marks}) LIMIT 1''',
        [run.snapshot, *sources]).fetchone() is not None


def _detail_results(run, adapters, stop, batch, commit):
    """Lease only free channel slots; multiplex completions on the SQLite owner.

    Each call has a daemon thread so abandoned adapter calls neither consume a
    future channel slot nor prevent process exit. Late results are discarded.
    Rate spacing is shared even across timed-out calls; logical concurrency is
    bounded, although Python cannot terminate an abandoned adapter thread.
    """
    futures = {}
    running = dict.fromkeys(run.channels, 0)
    fetch_options = {}
    for source, adapter in adapters.items():
        options = {}
        max_comments = run.config.get('youtube', {}).get('max_comments') or 0
        if source == 'youtube' and max_comments > 0:
            # Optional adapter contract: fetch(item, *, max_comments=N), or
            # **kwargs. Inspect before calling; never retry a fetch on TypeError.
            try:
                inspect.signature(adapter.fetch).bind(None, max_comments=max_comments)
            except (TypeError, ValueError):
                pass  # Legacy/uninspectable adapters keep their original call.
            else:
                options['max_comments'] = max_comments
        fetch_options[source] = options

    def call(future, row, started):
        try:
            run.limiters[row.source].wait_start()
            started.append(time.monotonic())
            docs = adapters[row.source].fetch(
                ListItem(row.url_norm, row.title, row.snippet, row.date, row.src_meta),
                **fetch_options[row.source])
            if not isinstance(docs, list) or any(not isinstance(d, FetchedDoc) for d in docs):
                raise AdapterParseError('Expected a list of FetchedDoc records')
            future.set_result(docs)
        except BaseException as exc:
            future.set_exception(exc)

    while True:
        run.tick()
        if (len(batch) + len(futures) >= BATCH_SIZE or any(
                sum(key[1] == source for key in batch) >= limiter.concurrency
                for source, limiter in run.limiters.items())):
            commit()
        for source in run.channels:
            while (not stop.is_set() and not run.target_reached() and run.active(source)
                   and running[source] < run.limiters[source].concurrency
                   and len(batch) + len(futures) < BATCH_SIZE):
                rows = run.q.lease_urls(run.snapshot, 1, LEASE_SECONDS, sources=[source])
                if not rows:
                    break
                row = rows[0]
                if row.exhausted:
                    yield row, None, None
                    continue
                future, started = Future(), []
                futures[future] = (row, started)
                running[source] += 1
                threading.Thread(target=call, args=(future, row, started), daemon=True).start()
        if not futures:
            if stop.is_set() or run.target_reached() or not _remaining(run):
                break
            stop.wait(0.05)
            continue
        done, _ = wait(futures, timeout=0.01, return_when=FIRST_COMPLETED)
        now = time.monotonic()
        expired = {f for f, (_, started) in futures.items()
                   if f not in done and started and now - started[0] >= FETCH_TIMEOUT_S}
        for future in done | expired:
            row, _ = futures.pop(future)
            running[row.source] -= 1
            if future in expired:
                result, error = None, TimeoutError(f'Fetch exceeded {FETCH_TIMEOUT_S}s')
            else:
                try:
                    result, error = future.result(), None
                except Exception as exc:
                    result, error = None, exc
            run.outcome(row.source, error)
            yield row, result, error


def run_detail(sid, snapshot_id, *, collection=None, filters=None, limiters=None, backoff_s=1):
    _load_hook()
    root, _, _, config = _inputs(sid, collection)
    filters = filters or FilterConfig(**config.get('filters', {}))
    q = CrawlQueue(root / 'queue.sqlite')
    try:
        sources = [r[0] for r in q.connection.execute('SELECT DISTINCT source FROM snapshot_urls WHERE snapshot_id=?', (snapshot_id,))]
    finally:
        q.close()
    resources = ExitStack()
    run = None
    writer = None
    status = 'interrupted'
    batch = {}
    written = 0
    def commit():
        nonlocal written
        if batch:
            writer.flush_and_fsync()
            run.q.mark_done_many(list(batch.values()))
            batch.clear()  # Completion is NOT idempotent; never replay a committed batch.
            written = 0
    try:
        adapters = {s: resources.enter_context(managed_adapter(REGISTRY[s])) for s in sources}
        run = _Run(root, sid, 'detail', sources, limiters, config, snapshot_id)
        run.share_naver_search_limiter(adapters)
        writer = DocWriter(root / 'docs', shard_size=5000)
        run.q.lease_urls(snapshot_id, 0, LEASE_SECONDS)  # Validate snapshot, apply exclusions.
        with _stop_event() as stop:
            for row, fetched, error in _detail_results(run, adapters, stop, batch, commit):
                last_error = safe_error(row.last_error) if row.last_error else None
                if error:
                    last_error = _error(error)
                    result = run.q.mark_failed_attempt(row.url_norm, row.source, last_error,
                                                      max_attempts=3, backoff_s=backoff_s,
                                                      blocked=isinstance(error, AdapterBlocked))
                    if result != 'exhausted':
                        continue
                fallback = row.exhausted or error is not None
                if fallback:
                    fetched = [FetchedDoc(row.title, row.snippet, [], row.date, row.src_meta, 'public', None)]
                docs, rules = [], []
                for item in fetched:
                    rule = check_doc(item, filters)
                    if rule:
                        rules.append(rule)
                    else:
                        docs.append(_doc(row, item, 'snippet' if fallback or item.access == 'restricted' else 'full'))
                if not docs and rules:
                    run.q.mark_filtered(row.url_norm, row.source, rules[0])
                    continue
                docs = list({d.doc_id: d for d in docs}.values())
                for doc in docs:
                    writer.write(doc)
                    written += 1
                    if written >= BATCH_SIZE:
                        # A URL can contain >200 threads. Its completion waits for all.
                        writer.flush_and_fsync()
                        commit()
                        written = 0
                level = 'snippet' if fallback or any(d.fetch_level == 'snippet' for d in docs) else 'full'
                access = 'restricted' if any(d.access == 'restricted' for d in docs) else 'public'
                batch[(row.url_norm, row.source)] = (row.url_norm, row.source, len(docs), last_error, level, access)
                # Include accepted, uncommitted documents so refilling slots cannot
                # run past the target while waiting for a completion transaction.
                run.completed_docs += len(docs)
                if len(batch) >= BATCH_SIZE:
                    commit()
            commit()
            status = 'done' if run.target_reached() else ('stopped' if stop.is_set() else 'done')
    finally:
        # Never complete pending writes after fencing or another exception.
        try:
            if writer is not None:
                writer.close()
        finally:
            try:
                if run is not None:
                    run.close(status)
            finally:
                resources.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=['list', 'detail'])
    parser.add_argument('--sid', required=True)
    parser.add_argument('--snapshot')
    parser.add_argument('--collection', type=Path)
    args = parser.parse_args(argv)
    if args.kind == 'detail' and not args.snapshot:
        parser.error('detail requires --snapshot')
    try:
        if args.kind == 'list':
            print(run_list(args.sid, collection=args.collection))
        else:
            run_detail(args.sid, args.snapshot, collection=args.collection)
            from app.crawl import control
            from app import autochain
            if control.phase_state(args.sid) == 'done':
                autochain.after_crawl(args.sid)
    except Exception as exc:
        print(f'Worker error: {_error(exc)}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
