"""Offline shared-host safety contracts; no external requests."""
from contextlib import closing
from threading import Barrier

import httpx
import pytest

from app.context import store
from app.crawl import worker
from app.crawl.adapters import REGISTRY
from app.crawl.adapters.base import AdapterBlocked
from app.crawl.adapters.naver_blog import NaverBlogAdapter
from app.crawl.adapters.naver_cafe import NaverCafeAdapter
from app.crawl.queue import CrawlQueue
from app.crawl.ratelimit import ChannelLimiter

CLASSES = (NaverBlogAdapter, NaverCafeAdapter)
SOURCES = tuple(cls.source for cls in CLASSES)
EMPTY = '<div class="not_found">검색 결과가 없습니다</div>'


@pytest.fixture
def fake_time(monkeypatch):
    ticks = [0.0]

    def sleep(seconds):
        ticks[0] += seconds

    def limiter(concurrency, interval):
        return ChannelLimiter(concurrency, interval, rng=lambda: 0.5,
                              clock=lambda: ticks[0], sleep=sleep)

    monkeypatch.setattr(worker, 'ChannelLimiter', limiter)
    return ticks, limiter


def register(monkeypatch, client):
    adapters = {cls.source: cls(client, sleep=lambda _: None) for cls in CLASSES}
    for source, adapter in adapters.items():
        monkeypatch.setitem(REGISTRY, source, lambda adapter=adapter: adapter)
    return adapters


@pytest.mark.parametrize('status', [200, 403, 500])
@pytest.mark.parametrize('kind', ['list', 'detail'])
def test_search_block_stops_host(tmp_path, monkeypatch, fake_time, status, kind):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status, text='검색 서비스 이용이 제한되었습니다')

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        adapters = register(monkeypatch, client)
        if kind == 'list':
            worker.run_list('S', collection=tmp_path, keywords=['k'], sources=SOURCES)
        else:
            with closing(CrawlQueue(tmp_path / 'queue.sqlite')) as q:
                q.add_list_tasks(worker._keywords(['k']), SOURCES)
                q.add_urls([dict(url=f'https://{a.kind}.naver.com/owner/1', source=s, kw='k')
                            for s, a in adapters.items()])
                snapshot = q.take_snapshot()
            for adapter in adapters.values():
                def fetch(item, adapter=adapter):
                    adapter.list_page('k')
                    return []
                monkeypatch.setattr(adapter, 'fetch', fetch)
            worker.run_detail('S', snapshot, collection=tmp_path, backoff_s=0)
        state = store.read_json(tmp_path / 'worker_state.json')
        assert {c['status'] for c in state['channels'].values()} == {'paused_blocked'}
        assert len(calls) == 1
        calls.clear()
        before = fake_time[0][0]
        for adapter in adapters.values():
            with pytest.raises(AdapterBlocked) as caught:
                adapter.list_page('later')
            assert caught.value.host == 'search.naver.com'
        assert calls == []
        assert fake_time[0][0] == before  # Already blocked requests do not wait.


def test_shared_search_limiter_spacing(tmp_path, monkeypatch, fake_time):
    ticks, _ = fake_time
    starts = []
    barrier = Barrier(2)

    def handle(request):
        assert request.url.host == 'search.naver.com'
        starts.append(ticks[0])
        return httpx.Response(200, text=EMPTY)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        adapters = register(monkeypatch, client)
        for adapter in adapters.values():
            original = adapter.list_page
            def list_page(kw, cursor=None, original=original):
                barrier.wait(timeout=5)
                return original(kw, cursor)
            monkeypatch.setattr(adapter, 'list_page', list_page)
        worker.run_list('S', collection=tmp_path, keywords=['k'], sources=SOURCES)
        assert len(starts) == 2
        assert starts[1] - starts[0] >= 0.5
        assert adapters[SOURCES[0]].search_limiter is adapters[SOURCES[1]].search_limiter


@pytest.mark.parametrize('cls,host', [
    (NaverBlogAdapter, 'blog.naver.com'),
    (NaverBlogAdapter, 'm.blog.naver.com'),
    (NaverCafeAdapter, 'article.cafe.naver.com'),
])
def test_article_hosts_use_channel_limiter(fake_time, cls, host):
    ticks, limiter = fake_time
    starts = []
    with httpx.Client(transport=httpx.MockTransport(
            lambda request: (starts.append(ticks[0]) or httpx.Response(200)))) as client:
        adapter = cls(client)
        assert adapter.search_limiter is adapter._limiter
        assert adapter.search_limiter.blocked is False
        adapter._limiter = limiter(1, 0.5)
        shared = limiter(1, 10)
        shared.blocked = True
        adapter.search_limiter = shared
        adapter.request(f'https://{host}/owner/1')
        adapter.request(f'https://{host}/owner/2')
        assert starts == [0.0, 0.5]
        assert shared._next == 0


@pytest.mark.parametrize('kind', ['list', 'detail'])
@pytest.mark.parametrize('sources,options,expected', [
    (SOURCES, {}, 0.5),
    (SOURCES, {'naver_blog': {'min_interval_s': 0.7},
               'naver_cafe': {'min_interval_s': 1.2}}, 1.2),
    (('naver_blog',), {'naver_blog': {'min_interval_s': 0.2}}, 0.2),
    (('naver_cafe',), {}, 0.5),
    (SOURCES, {s: {'min_interval_s': 0} for s in SOURCES}, 0),
])
def test_worker_shared_limiter_configuration(tmp_path, monkeypatch, fake_time, kind, sources, options, expected):
    store.write_json(tmp_path / 'manifest.json', {'config': {'perChannel': options}})
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=EMPTY))) as client:
        adapters = register(monkeypatch, client)
        if kind == 'list':
            worker.run_list('S', collection=tmp_path, keywords=['k'], sources=sources)
        else:
            with closing(CrawlQueue(tmp_path / 'queue.sqlite')) as q:
                q.add_list_tasks(worker._keywords(['k']), sources)
                q.add_urls([dict(url=f'https://{adapters[s].kind}.naver.com/owner/1', source=s, kw='k')
                            for s in sources])
                snapshot = q.take_snapshot()
            for adapter in adapters.values():
                monkeypatch.setattr(adapter, 'fetch', lambda item: [])
            worker.run_detail('S', snapshot, collection=tmp_path)
        shared = adapters[sources[0]].search_limiter
        assert all(adapters[s].search_limiter is shared for s in sources)
        assert all(adapters[s]._limiter is not shared for s in sources)
        assert (shared.concurrency, shared.min_interval_s, shared.jitter) == (1, expected, 0.2)
        assert shared.blocked is False


def test_other_blocks_keep_twenty_consecutive_rule(tmp_path):
    run = worker._Run(tmp_path, 'S', 'list', SOURCES, None, {})
    try:
        for _ in range(19):
            run.outcome('naver_blog', AdapterBlocked('HTTP 403'))
        assert all(run.active(s) for s in SOURCES)
        run.outcome('naver_blog', AdapterBlocked('HTTP 429'))
        assert run.channels['naver_blog']['status'] == 'paused_blocked'
        assert run.active('naver_cafe')
    finally:
        run.close('done')
