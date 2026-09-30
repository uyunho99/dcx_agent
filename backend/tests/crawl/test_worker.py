from contextlib import closing
import csv
import json
from dataclasses import replace

import pytest

from app.config import settings
from app.crawl import worker
from app.crawl.adapters import REGISTRY
from app.crawl.adapters.base import AdapterBlocked
from app.crawl.adapters.fixture import FixtureAdapter
from app.crawl.filters import FilterConfig
from app.crawl.queue import CrawlQueue
from app.crawl.schema import Doc
from app.crawl.writer import read_docs


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    path = tmp_path / 'corpus.csv'
    with path.open('w') as f:
        w = csv.writer(f)
        w.writerow(['review'])
        w.writerows([[f'에어컨 소음 {i}'] for i in range(80)])
    monkeypatch.setattr(settings, 'fixture_corpus_path', str(path))
    monkeypatch.setattr(settings, 'enable_fixture_channel', True)
    monkeypatch.setattr(settings, 'author_salt_path', str(tmp_path / '.salt'))
    return path


def setup_list(tmp_path, **kwargs):
    return worker.run_list('S', collection=tmp_path, keywords=['에어컨'],
                           sources=['fixture'], filters=FilterConfig(date_from=None, date_to=None), **kwargs)


def detail(tmp_path, snapshot, **kwargs):
    return worker.run_detail('S', snapshot, collection=tmp_path,
                            filters=FilterConfig(date_from=None, date_to=None), backoff_s=0.001, **kwargs)


def state(path):
    return json.loads((path / 'worker_state.json').read_text())['channels']


def test_list_then_detail_writes_docs(tmp_path, corpus):
    snapshot = setup_list(tmp_path)
    detail(tmp_path, snapshot)
    docs = list(read_docs(tmp_path / 'docs'))
    assert len(docs) == 80
    assert all(set(d) == set(Doc.model_fields) for d in docs)
    assert all(d['kw_hits'] == ['에어컨'] and d['kw'] == '에어컨' for d in docs)
    assert all(Doc.model_validate(d) for d in docs)


def test_fetch_failure_falls_back_to_snippet(tmp_path, corpus, monkeypatch):
    snapshot = setup_list(tmp_path)
    calls = []
    class Broken(FixtureAdapter):
        def fetch(self, item):
            calls.append(item.url)
            raise OSError('offline')
    monkeypatch.setitem(REGISTRY, 'fixture', lambda: Broken(corpus))
    detail(tmp_path, snapshot)
    docs = list(read_docs(tmp_path / 'docs'))
    assert len(calls) == 240 and len(docs) == 80
    assert all(d['fetch_level'] == 'snippet' for d in docs)
    q = CrawlQueue(tmp_path / 'queue.sqlite')
    assert q.counts()['done'] == 80
    assert all(r[0] == 'OSError' for r in q.connection.execute('SELECT last_error FROM urls'))
    q.close()


def test_blocked_channel_pauses_only_that_channel(tmp_path, corpus, monkeypatch):
    class Blocked(FixtureAdapter):
        def fetch(self, item):
            raise AdapterBlocked('403')
    monkeypatch.setitem(REGISTRY, 'naver_blog', lambda: Blocked(corpus))
    snap = worker.run_list('S', collection=tmp_path, keywords=['에어컨'],
                           sources=['fixture', 'naver_blog'], filters=FilterConfig(date_from=None, date_to=None))
    detail(tmp_path, snap)
    assert state(tmp_path)['naver_blog']['status'] == 'paused_blocked'
    assert state(tmp_path)['naver_blog']['blocked'] >= 20
    assert len([d for d in read_docs(tmp_path / 'docs') if d['source'] == 'fixture']) == 80


def test_restricted_recorded(tmp_path, corpus, monkeypatch):
    snapshot = setup_list(tmp_path)
    class Restricted(FixtureAdapter):
        def fetch(self, item):
            return [replace(super().fetch(item)[0], access='restricted', author_raw='private-id')]
    monkeypatch.setitem(REGISTRY, 'fixture', lambda: Restricted(corpus))
    detail(tmp_path, snapshot)
    docs = list(read_docs(tmp_path / 'docs'))
    assert all(d['access'] == 'restricted' and len(d['author_hash']) == 16 for d in docs)
    assert 'private-id' not in ''.join(p.read_text() for p in (tmp_path / 'docs').glob('*'))


def test_list_dropped_invalid_url(tmp_path, monkeypatch):
    from app.crawl.adapters.base import ListItem, ListPage
    class Invalid:
        def list_page(self, kw, cursor):
            return ListPage([ListItem('', '광고', '', None, {})], None, 1)
    original = CrawlQueue.record_list_page
    monkeypatch.setattr(CrawlQueue, 'record_list_page',
                        lambda self, task, items, cursor, **kwargs: original(self, task, [], cursor))
    monkeypatch.setitem(REGISTRY, 'fixture', Invalid)
    assert setup_list(tmp_path)


def seed_channels(tmp_path, sizes):
    from app.crawl.queue import KwMeta
    with closing(CrawlQueue(tmp_path / 'queue.sqlite')) as q:
        q.add_list_tasks([KwMeta('k1', '', '', 0), KwMeta('k2', '', '', 1)], [])
        q.add_urls([dict(url=f'fixture://aircon/{i:04}', source=s, kw=f'k{k+1}')
                    for k, (s, n) in enumerate(sizes) for i in range(n)])
        return q.take_snapshot()


def test_bounded_claims_interrupt_resume(tmp_path, monkeypatch):
    import threading
    from contextlib import contextmanager
    from collections import Counter
    from app.crawl.adapters.base import FetchedDoc
    from app.crawl.ratelimit import ChannelLimiter
    snap = seed_channels(tmp_path, [('fixture', 3000), ('naver_blog', 3)])
    stop = threading.Event()
    calls = Counter()
    main = threading.get_ident()
    original = CrawlQueue.lease_urls
    def lease(self, *args, **kwargs):
        assert threading.get_ident() == main
        rows = original(self, *args, **kwargs)
        for s in ('fixture', 'naver_blog'):
            assert self.connection.execute("SELECT count(*) FROM urls WHERE source=? AND status='leased'", (s,)).fetchone()[0] <= 4
            count = self.connection.execute("SELECT count(*) FROM urls WHERE source=? AND attempts>0", (s,)).fetchone()[0]
            if not resumed[0]:
                assert count <= 4
        return rows
    class Adapter:
        def fetch(self, item):
            calls[item.url] += 1
            if not resumed[0]:
                stop.set()
            return [FetchedDoc('', 'body', [], None, {}, 'public', None)]
    @contextmanager
    def stopping():
        yield stop
    resumed = [False]
    monkeypatch.setattr(worker, '_stop_event', stopping)
    monkeypatch.setattr(CrawlQueue, 'lease_urls', lease)
    for s in ('fixture', 'naver_blog'):
        monkeypatch.setitem(REGISTRY, s, Adapter)
    limits = {s: ChannelLimiter(2, 0) for s in ('fixture', 'naver_blog')}
    detail(tmp_path, snap, limiters=limits)
    resumed[0] = True
    stop.clear()
    detail(tmp_path, snap, limiters=limits)
    with closing(CrawlQueue(tmp_path / 'queue.sqlite')) as q:
        assert q.counts()['done'] == 3003
        assert all(r['attempts'] == 1 for r in q.connection.execute('SELECT attempts FROM urls'))
    assert sum(calls.values()) == 3003


def test_fast_channel_finishes_before_slow_call(tmp_path, monkeypatch):
    import threading
    from app.crawl.adapters.base import FetchedDoc
    from app.crawl.ratelimit import ChannelLimiter
    snap = seed_channels(tmp_path, [('fixture', 205), ('naver_blog', 1)])
    finished = threading.Event()
    observed = []
    calls = []
    class Fast:
        def fetch(self, item):
            calls.append(item.url)
            if len(calls) == 205:
                finished.set()
            return [FetchedDoc('', 'body', [], None, {}, 'public', None)]
    class Slow(Fast):
        def fetch(self, item):
            observed.append(finished.wait(2))
            return [FetchedDoc('', 'body', [], None, {}, 'public', None)]
    monkeypatch.setitem(REGISTRY, 'fixture', Fast)
    monkeypatch.setitem(REGISTRY, 'naver_blog', Slow)
    detail(tmp_path, snap, limiters={s: ChannelLimiter(1, 0) for s in ('fixture', 'naver_blog')})
    assert observed == [True]


def test_hung_fetch_times_out_and_channel_continues(tmp_path, monkeypatch):
    import threading
    from app.crawl.adapters.base import FetchedDoc
    from app.crawl.ratelimit import ChannelLimiter
    snap = seed_channels(tmp_path, [('fixture', 3)])
    release = threading.Event()
    calls = []
    class Hanging:
        def fetch(self, item):
            calls.append(item.url)
            if item.url.endswith('/0000'):
                release.wait(2)
            return [FetchedDoc('', 'body', [], None, {}, 'public', None)]
    monkeypatch.setattr(worker, 'FETCH_TIMEOUT_S', 0.03, raising=False)
    monkeypatch.setitem(REGISTRY, 'fixture', Hanging)
    try:
        detail(tmp_path, snap, limiters={'fixture': ChannelLimiter(1, 0)})
        assert not release.is_set()
        with closing(CrawlQueue(tmp_path / 'queue.sqlite')) as q:
            row = q.connection.execute("SELECT * FROM urls WHERE url_norm LIKE '%0000'").fetchone()
            assert row['attempts'] == 3
            assert 'TimeoutError' in row['last_error']
            assert row['fetch_level'] == 'snippet'
            assert q.counts()['done'] == 3
        assert len(calls) == 5
    finally:
        release.set()


def write_limits(root, config):
    (root / 'manifest.json').write_text(json.dumps({'config': config}))


@pytest.mark.parametrize('config, expected', [
    ({'perChannel': {'fixture': {'max_per_keyword': 5}, 'youtube': {'max_per_keyword': 7}}}, {'fixture': 5, 'youtube': 7}),
    ({'youtube': {'videos_per_keyword': 5}}, {'fixture': 12, 'youtube': 5}),
    ({'perChannel': {'youtube': {'max_per_keyword': 7}}, 'youtube': {'videos_per_keyword': 5}}, {'fixture': 12, 'youtube': 5}),
    ({}, {'fixture': 12, 'youtube': 12}),
    ({'perChannel': {'fixture': {'max_per_keyword': 0}}, 'youtube': {'videos_per_keyword': 0}}, {'fixture': 12, 'youtube': 12}),
])
def test_listing_limits_per_keyword_source(tmp_path, monkeypatch, config, expected):
    from collections import Counter
    from app.crawl.adapters.base import ListItem, ListPage
    calls = Counter()
    class Pages:
        def __init__(self, source):
            self.source = source
        def list_page(self, kw, cursor):
            calls[kw, self.source] += 1
            start = int(cursor or 0)
            return ListPage([ListItem(f'https://example.com/{kw}/{i}', '', '', None, {})
                             for i in range(start, start + 4)],
                            str(start + 4) if start < 8 else None, 12)
    # Register the fake YouTube source through the worker's existing module hook.
    (tmp_path / 'limit_adapter_hook.py').write_text(
        'from app.crawl.adapters import REGISTRY\nREGISTRY["youtube"] = REGISTRY["fixture"]\n')
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv('DCX_TEST_ADAPTER_MODULE', 'limit_adapter_hook')
    monkeypatch.delitem(__import__('sys').modules, 'limit_adapter_hook', raising=False)
    monkeypatch.setitem(REGISTRY, 'youtube', None)
    monkeypatch.setitem(REGISTRY, 'fixture', lambda: Pages('youtube'))
    worker._load_hook()
    monkeypatch.setitem(REGISTRY, 'fixture', lambda: Pages('fixture'))
    write_limits(tmp_path, config)
    for _ in range(2):
        worker.run_list('S', collection=tmp_path, keywords=['k1', 'k2'], sources=['fixture', 'youtube'],
                        filters=FilterConfig(date_from=None, date_to=None))
    with closing(CrawlQueue(tmp_path / 'queue.sqlite')) as q:
        for kw in ('k1', 'k2'):
            for source, count in expected.items():
                assert q.connection.execute('SELECT count(*) FROM url_hits WHERE kw=? AND source=?',
                                            (kw, source)).fetchone()[0] == count
                assert calls[kw, source] == (count + 3) // 4
        assert not q.connection.execute("SELECT 1 FROM list_tasks WHERE status!='done'").fetchone()


@pytest.mark.parametrize('accepts_option', [True, False])
@pytest.mark.parametrize('limit', [None, 0, 17])
def test_youtube_max_comments_option(tmp_path, monkeypatch, accepts_option, limit):
    from app.crawl.adapters.base import FetchedDoc
    snap = seed_channels(tmp_path, [('youtube', 2)])
    received = []
    class Adapter:
        def fetch(self, item, *, max_comments=None):
            received.append(max_comments)
            return [FetchedDoc('', 'body', [], None, {}, 'public', None)]
    class Legacy:
        def fetch(self, item):
            return Adapter().fetch(item)
    monkeypatch.setitem(REGISTRY, 'youtube', Adapter if accepts_option else Legacy)
    write_limits(tmp_path, {'youtube': {} if limit is None else {'max_comments': limit}})
    detail(tmp_path, snap)
    assert received == [17 if accepts_option and limit == 17 else None] * 2
    assert len(list(read_docs(tmp_path / 'docs'))) == 2


@pytest.mark.parametrize('target', [None, 0, 13])
def test_target_total_counts_documents_and_drains_calls(tmp_path, monkeypatch, target):
    from app.crawl.adapters.base import FetchedDoc
    from app.crawl.ratelimit import ChannelLimiter
    snap = seed_channels(tmp_path, [('fixture', 90)])
    calls = []
    class Adapter:
        def fetch(self, item):
            calls.append(item.url)
            return [FetchedDoc('', 'body', [], None, {}, 'public', None, str(i)) for i in range(3)]
    monkeypatch.setitem(REGISTRY, 'fixture', Adapter)
    write_limits(tmp_path, {} if target is None else {'target_total': target})
    detail(tmp_path, snap, limiters={'fixture': ChannelLimiter(4, 0)})
    with closing(CrawlQueue(tmp_path / 'queue.sqlite')) as q:
        counts = q.counts()
        assert counts['doc_count'] == len(list(read_docs(tmp_path / 'docs'))) == len(calls) * 3
        assert q.connection.execute("SELECT status FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()[0] == 'done'
        assert not q.connection.execute("SELECT 1 FROM urls WHERE status NOT IN ('pending','done')").fetchone()
        if target:
            assert target <= counts['doc_count'] <= target + worker.BATCH_SIZE
            assert counts['pending'] > 0
            assert not q.connection.execute("SELECT 1 FROM urls WHERE status='pending' AND attempts!=0").fetchone()
        else:
            assert counts['doc_count'] == 270
    saved = json.loads((tmp_path / 'worker_state.json').read_text())
    assert saved.get('stopReason') == ('target_reached' if target else None)
    if target:
        before = len(calls)
        detail(tmp_path, snap)
        assert len(calls) == before
        assert json.loads((tmp_path / 'worker_state.json').read_text())['stopReason'] == 'target_reached'


@pytest.mark.parametrize('stage', ['list', 'detail'])
@pytest.mark.parametrize('failure', [False, True])
def test_worker_closes_adapter(tmp_path, corpus, monkeypatch, stage, failure):
    snapshot = setup_list(tmp_path) if stage == 'detail' else None
    closed = []
    class Owned(FixtureAdapter):
        def close(self):
            closed.append(self)
    monkeypatch.setitem(REGISTRY, 'fixture', lambda: Owned(corpus))
    if failure:
        def fail(*args, **kwargs):
            raise RuntimeError('coordinator failed')
        monkeypatch.setattr(worker._Run, 'tick', fail)
    def run():
        return setup_list(tmp_path) if stage == 'list' else detail(tmp_path, snapshot)
    if failure:
        with pytest.raises(RuntimeError, match='coordinator failed'):
            run()
    else:
        run()
    assert len(closed) == 1


@pytest.mark.parametrize('stage', ['list', 'detail'])
@pytest.mark.parametrize('failure', ['factory', 'run'])
def test_worker_closes_adapters_on_setup_failure(tmp_path, corpus, monkeypatch, stage, failure):
    snapshot = setup_list(tmp_path) if stage == 'detail' else None
    closed = []
    class Owned(FixtureAdapter):
        def close(self):
            closed.append(self)
    def fail(*args, **kwargs):
        raise RuntimeError('setup failed')
    monkeypatch.setitem(REGISTRY, 'fixture', lambda: Owned(corpus))
    if failure == 'factory':
        monkeypatch.setitem(REGISTRY, 'broken', fail)
        if stage == 'detail':
            with closing(CrawlQueue(tmp_path / 'queue.sqlite')) as q:
                q.add_urls([dict(url='fixture://aircon/broken', source='broken', kw='k')])
                snapshot = q.take_snapshot()
    else:
        monkeypatch.setattr(worker, '_Run', fail)
    with pytest.raises(RuntimeError, match='setup failed'):
        if stage == 'list':
            worker.run_list('S', collection=tmp_path, keywords=['k'],
                            sources=['fixture', 'broken'] if failure == 'factory' else ['fixture'])
        else:
            detail(tmp_path, snapshot)
    assert len(closed) == 1
