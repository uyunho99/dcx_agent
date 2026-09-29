import collections
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from app.crawl import healthcheck, worker
from app.crawl.adapters import REGISTRY
from app.crawl.adapters.base import ListPage
from app.crawl.adapters.fixture import FixtureAdapter
from app.crawl.filters import FilterConfig
from app.crawl.queue import CrawlQueue, LeaseLost
from app.crawl.ratelimit import ChannelLimiter
from app.crawl.writer import DocWriter, read_docs
from test_worker import corpus, detail, setup_list, state


def test_kill_and_resume_no_refetch(tmp_path, corpus):
    corpus.write_text('review\n' + ''.join(f'에어컨 소음 {i}\n' for i in range(520)))
    snap = setup_list(tmp_path)
    hook = tmp_path / 'count_adapter.py'
    hook.write_text('''import os, time
from app.crawl.adapters import REGISTRY
from app.crawl.adapters.fixture import FixtureAdapter
class Counted(FixtureAdapter):
    def fetch(self, item):
        fd = os.open(os.environ['FETCH_LOG'], os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.write(fd, (item.url + '\\n').encode())
        os.close(fd)
        time.sleep(0.025)
        return super().fetch(item)
REGISTRY['fixture'] = lambda: Counted(os.environ['FIXTURE_CORPUS_PATH'])
''')
    # CLI loads filter settings from the collection manifest.
    (tmp_path / 'manifest.json').write_text(json.dumps({'config': {'filters': {'date_from': None, 'date_to': None}}}))
    log = tmp_path / 'fetch.log'
    env = dict(os.environ, DCX_TEST_ADAPTER_MODULE='count_adapter', FETCH_LOG=str(log),
               FIXTURE_CORPUS_PATH=str(corpus), ENABLE_FIXTURE_CHANNEL='true',
               PYTHONPATH=str(tmp_path) + os.pathsep + str(Path.cwd()))
    cmd = [sys.executable, '-m', 'app.crawl.worker', 'detail', '--sid', 'S',
           '--snapshot', snap, '--collection', str(tmp_path)]
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 8
        committed = set()
        while not committed:
            assert proc.poll() is None
            assert time.monotonic() < deadline
            with CrawlQueue.open_readonly(tmp_path / 'queue.sqlite') as db:
                committed = {r[0] for r in db.execute("SELECT url_norm FROM urls WHERE status='done'")}
            time.sleep(0.005)
        proc.kill()
        proc.communicate(timeout=3)
        # Include transactions committed between the successful poll and SIGKILL.
        with CrawlQueue.open_readonly(tmp_path / 'queue.sqlite') as db:
            committed = {r[0] for r in db.execute("SELECT url_norm FROM urls WHERE status='done'")}
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    counts = collections.Counter(log.read_text().splitlines())
    assert committed
    assert all(counts[url] == 1 for url in committed)
    assert len(counts) == 520 and max(counts.values()) <= 2
    assert sum(n > 1 for n in counts.values()) <= 200
    docs = list(read_docs(tmp_path / 'docs'))
    assert len(docs) == len({d['doc_id'] for d in docs}) == 520


def test_reader_skips_truncated_last_line(tmp_path, caplog):
    (tmp_path / 'shard-0001.jsonl').write_bytes(b'{"doc_id":"a"}\n\xff\n{"broken":')
    assert list(read_docs(tmp_path)) == [{'doc_id': 'a'}]
    assert 'Skipping' in caplog.text


def test_fsync_before_done(tmp_path, corpus, monkeypatch):
    snap = setup_list(tmp_path)
    docsdir = tmp_path / 'docs'
    docsdir.mkdir()
    (docsdir / 'shard-0001.jsonl').write_text('{"truncated":')
    original = CrawlQueue.mark_done_many
    calls = []
    flushed = []
    fsync = DocWriter.flush_and_fsync
    def flush(self):
        fsync(self)
        flushed.append(True)
    def commit(self, rows):
        assert flushed
        flushed.clear()
        docs = list(read_docs(docsdir))
        assert all(any(d['url'] == row[0] for d in docs) for row in rows)
        assert len(rows) == len({r[:2] for r in rows}) <= 200
        calls.append(rows)
        if len(calls) == 1:
            raise RuntimeError('crash after fsync before commit')
        original(self, rows)
    monkeypatch.setattr(DocWriter, 'flush_and_fsync', flush)
    monkeypatch.setattr(CrawlQueue, 'mark_done_many', commit)
    with pytest.raises(RuntimeError, match='crash after fsync'):
        detail(tmp_path, snap)
    q = CrawlQueue(tmp_path / 'queue.sqlite')
    assert q.counts()['done'] == 0
    q.close()
    detail(tmp_path, snap)
    assert len(calls) >= 2 and len(list(read_docs(docsdir))) == 80


def test_channels_and_keywords_run_concurrently(tmp_path, monkeypatch):
    lock = threading.Lock()
    active = collections.Counter()
    peak = collections.Counter()
    both = []
    class Slow:
        def __init__(self, source): self.source = source
        def list_page(self, kw, cursor):
            with lock:
                active[self.source] += 1
                peak[self.source] = max(peak[self.source], active[self.source])
                both.append(sum(v > 0 for v in active.values()))
            time.sleep(0.2)
            with lock: active[self.source] -= 1
            return ListPage([], None, 0)
    for src in ['fixture', 'naver_blog']:
        monkeypatch.setitem(REGISTRY, src, lambda src=src: Slow(src))
    start = time.monotonic()
    worker.run_list('S', collection=tmp_path, keywords=['a', 'b', 'c'], sources=['fixture', 'naver_blog'])
    assert time.monotonic() - start < 0.6
    assert max(both) == 2 and all(1 < n <= 4 for n in peak.values())


def test_parse_error_rate_pauses_channel(tmp_path, corpus, monkeypatch):
    class Broken(FixtureAdapter):
        def fetch(self, item): raise ValueError('parser changed')
    monkeypatch.setitem(REGISTRY, 'naver_blog', lambda: Broken(corpus))
    snap = worker.run_list('S', collection=tmp_path, keywords=['에어컨'], sources=['fixture', 'naver_blog'],
                           filters=FilterConfig(date_from=None, date_to=None))
    detail(tmp_path, snap)
    assert state(tmp_path)['naver_blog']['status'] == 'paused_parse_error'
    assert state(tmp_path)['naver_blog']['attempts'] >= 10
    docs = list(read_docs(tmp_path / 'docs'))
    assert len([d for d in docs if d['source'] == 'fixture']) == 80
    assert all(d['fetch_level'] == 'snippet' for d in docs if d['source'] == 'naver_blog')


def test_healthcheck_reports_per_stage(corpus, capsys, monkeypatch):
    assert healthcheck.main(['--source', 'fixture']) == 0
    out = capsys.readouterr().out
    assert 'fixture' in out and 'list_ok 80/80 · detail_ok 3/3 · blocked false' in out
    class Broken(FixtureAdapter):
        def fetch(self, item): raise ValueError('parser')
    monkeypatch.setitem(REGISTRY, 'fixture', lambda: Broken(corpus))
    assert healthcheck.main(['--source', 'fixture']) != 0
    assert 'detail_ok FAIL' in capsys.readouterr().out


def test_same_snapshot_same_urls(tmp_path, corpus):
    snap = setup_list(tmp_path)
    detail(tmp_path, snap)
    before = {d['doc_id'] for d in read_docs(tmp_path / 'docs')}
    detail(tmp_path, snap)
    assert before == {d['doc_id'] for d in read_docs(tmp_path / 'docs')}


def test_limiter_fake_clock():
    now = [0.0]
    limiter = ChannelLimiter(2, 0.5, clock=lambda: now[0], sleep=lambda s: now.__setitem__(0, now[0] + s))
    starts = []
    for _ in range(3):
        with limiter: starts.append(now[0])
    assert starts == [0, 0.5, 1.0]


def test_lease_lost_does_not_commit(tmp_path, corpus, monkeypatch):
    snap = setup_list(tmp_path)
    def lost(self, rows): raise LeaseLost('fenced')
    monkeypatch.setattr(CrawlQueue, 'mark_done_many', lost)
    with pytest.raises(LeaseLost): detail(tmp_path, snap)
    q = CrawlQueue(tmp_path / 'queue.sqlite')
    assert q.counts()['done'] == 0
    assert q.connection.execute("SELECT status FROM runs WHERE kind='detail'").fetchone()[0] == 'interrupted'
    q.close()


def test_writer_rotation_and_first_wins(tmp_path):
    w = DocWriter(tmp_path, shard_size=2)
    for value in [1, 2, 3]: w.write({'doc_id': 'same' if value != 2 else 'other', 'value': value})
    w.close()
    assert len(list(tmp_path.glob('shard-*.jsonl'))) == 2
    assert [d['value'] for d in read_docs(tmp_path)] == [1, 2]


def test_heartbeat_during_slow_fetch_stays_on_main_thread(tmp_path, corpus, monkeypatch):
    snap = setup_list(tmp_path)
    main_thread = threading.get_ident()
    beats = []
    original = CrawlQueue.heartbeat
    def heartbeat(self, run_id):
        assert threading.get_ident() == main_thread
        beats.append(run_id)
        original(self, run_id)
    class Slow(FixtureAdapter):
        def fetch(self, item):
            assert threading.get_ident() != main_thread
            time.sleep(0.01)
            return super().fetch(item)
    monkeypatch.setitem(REGISTRY, 'fixture', lambda: Slow(corpus))
    monkeypatch.setattr(worker, 'HEARTBEAT_INTERVAL', 0.02)
    monkeypatch.setattr(CrawlQueue, 'heartbeat', heartbeat)
    detail(tmp_path, snap)
    assert len(beats) >= 2


def test_recovered_exhausted_rows_skip_fetch(tmp_path, corpus, monkeypatch):
    snap = setup_list(tmp_path)
    q = CrawlQueue(tmp_path / 'queue.sqlite')
    run_id = q.register_run('detail')
    for _ in range(3):
        rows = q.lease_urls(snap, 80, 60)
        for row in rows:
            q.mark_failed_attempt(row.url_norm, row.source, 'failure', backoff_s=0)
    q.finish_run(run_id, 'interrupted')
    q.close()
    class Never(FixtureAdapter):
        def fetch(self, item): pytest.fail('Exhausted URLs must not fetch')
    monkeypatch.setitem(REGISTRY, 'fixture', lambda: Never(corpus))
    detail(tmp_path, snap)
    assert len(list(read_docs(tmp_path / 'docs'))) == 80
    assert all(d['fetch_level'] == 'snippet' for d in read_docs(tmp_path / 'docs'))


def test_detail_channels_run_concurrently(tmp_path, corpus, monkeypatch):
    q = CrawlQueue(tmp_path / 'queue.sqlite')
    q.add_urls([dict(url=f'fixture://aircon/{i}', source=s, kw='에어컨')
                for s in ['fixture', 'naver_blog'] for i in range(3)])
    snap = q.take_snapshot()
    q.close()
    barrier = threading.Barrier(6)
    class Slow(FixtureAdapter):
        def fetch(self, item):
            barrier.wait(timeout=2)
            return super().fetch(item)
    for s in ['fixture', 'naver_blog']:
        monkeypatch.setitem(REGISTRY, s, lambda: Slow(corpus))
    detail(tmp_path, snap)
    assert len(list(read_docs(tmp_path / 'docs'))) == 6


def test_sigterm_commits_current_work(tmp_path, corpus, monkeypatch):
    snap = setup_list(tmp_path)
    class Terminate(FixtureAdapter):
        sent = False
        lock = threading.Lock()
        def fetch(self, item):
            with self.lock:
                if not self.sent:
                    self.sent = True
                    os.kill(os.getpid(), __import__('signal').SIGTERM)
            return super().fetch(item)
    monkeypatch.setitem(REGISTRY, 'fixture', lambda: Terminate(corpus))
    detail(tmp_path, snap)
    q = CrawlQueue(tmp_path / 'queue.sqlite')
    assert q.connection.execute("SELECT status FROM runs WHERE kind='detail'").fetchone()[0] == 'stopped'
    assert 0 < q.counts()['done'] < 80
    assert q.counts()['done'] == len(list(read_docs(tmp_path / 'docs')))
    q.close()


def test_cli_missing_collection_is_clear(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(worker, 'load_session', lambda sid: {})
    assert worker.main(['list', '--sid', 'S']) == 1
    assert 'no collectionId' in capsys.readouterr().err


def test_active_collection_location(tmp_path, corpus, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, 'local_data_dir', str(tmp_path))
    monkeypatch.setattr(worker, 'load_session', lambda sid: {'collectionId': 'c1', 'keywords': ['에어컨']})
    worker.run_list('S', filters=FilterConfig(date_from=None, date_to=None))
    assert (tmp_path / 'crawl' / 'S' / 'collections' / 'c1' / 'queue.sqlite').exists()


def test_detail_channels_overlap_across_queue_batch_boundary(tmp_path, monkeypatch):
    from app.crawl.adapters.base import FetchedDoc
    q = CrawlQueue(tmp_path / 'queue.sqlite')
    q.add_urls([dict(url=f'fixture://aircon/{i:03}', source=s, kw='air')
                for s, n in [('fixture', 205), ('naver_blog', 3)] for i in range(n)])
    snap = q.take_snapshot()
    q.close()
    barrier = threading.Barrier(2)
    overlaps = []
    class Adapter:
        def fetch(self, item):
            if item.url.endswith('/000'):
                try:
                    barrier.wait(timeout=0.5)
                    overlaps.append(True)
                except threading.BrokenBarrierError:
                    overlaps.append(False)
            return [FetchedDoc('', 'body', [], None, {}, 'public', None)]
    for s in ['fixture', 'naver_blog']:
        monkeypatch.setitem(REGISTRY, s, Adapter)
    detail(tmp_path, snap)
    assert overlaps == [True, True]
    assert len(list(read_docs(tmp_path / 'docs'))) == 208
