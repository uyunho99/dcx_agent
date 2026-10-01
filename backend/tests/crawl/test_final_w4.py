import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from app.config import settings
from app.crawl import adapters, worker
from app.crawl.adapters.naver_cafe import NaverCafeAdapter
from app.crawl.adapters.youtube import YoutubeAdapter, _date
from app.crawl.filters import FilterConfig, check_list, check_doc
from app.external.base import integration_status


def test_integration_dependencies(monkeypatch):
    monkeypatch.setattr(settings, 'naver_client_id', 'configured')
    monkeypatch.setattr(settings, 'naver_client_secret', 'configured')
    entries = {e.name: e for e in integration_status()}
    assert not {'youtube', 'naver_search'} & entries.keys()
    assert set(entries) == {'openai', 'claude'}


def test_cheap_availability_and_offline_flag(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('availability constructed an HTTP client')
    monkeypatch.setattr(httpx, 'Client', forbidden)
    monkeypatch.setattr(settings, 'enable_fixture_channel', True)
    monkeypatch.setattr(settings, 'fixture_corpus_path', '/offline.csv')
    monkeypatch.setattr(settings, 'real_channels_enabled', False)
    assert adapters.available_sources() == ['fixture']
    for cls in (NaverCafeAdapter, adapters.NaverBlogAdapter, adapters.ClienAdapter,
                adapters.PpomppuAdapter, YoutubeAdapter):
        assert not cls.is_available()
    monkeypatch.setattr(settings, 'real_channels_enabled', True)
    assert len(adapters.available_sources()) == 6


@pytest.mark.parametrize('date_text,expected', [('2026. 9. 2.', '2026-09-02'), ('3일 전', '2026-09-26'), ('', None)])
def test_cafe_search_identity_and_restricted_dates(date_text, expected):
    markup = f'''<ul class="lst_view"><li><div class="user_info"><a class="name">중고나라</a>
    <span class="sub">{date_text}</span></div><a class="title_link" href="https://cafe.naver.com/joonggonara/123">제목</a>
    <a class="dsc_link">요약</a></li></ul>'''
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=markup))) as client:
        a = NaverCafeAdapter(client, now=lambda: datetime(2026, 9, 29, 12))
        item = a.list_page('keyword').items[0]
    assert item.date == expected
    assert item.src_meta['cafe'] == '중고나라'
    for identity in ('중고나라', 'joonggonara'):
        assert check_list(item, FilterConfig(date_from=None, date_to=None, ad_words=[], exclude_sources=[identity])) == '③'
    doc, = a.restricted_doc(item)
    assert doc.date == expected
    assert check_doc(doc, FilterConfig(date_from='2026-09-28', ad_words=[])) == ('①' if expected else None)


@pytest.mark.parametrize('number,status', [(1, 401), (3, 200)])
def test_detail_cafe_name(number, status):
    path = Path(__file__).parents[1] / f'fixtures/http/naver_cafe/detail-{number}.json'
    payload = json.loads(path.read_text())
    result = payload['result']
    expected = result['cafe']['name'] if result.get('cafe') else result['more']['cafeName']
    from app.crawl.adapters.base import ListItem
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=payload))) as client:
        doc, = NaverCafeAdapter(client).fetch(ListItem('https://cafe.naver.com/slug/123', 'title', 'snippet', None, {'cafe': 'old', 'cafe_id': 'slug'}))
    assert doc.src_meta['cafe'] == expected
    assert doc.src_meta['cafe_id'] == 'slug'


@pytest.mark.parametrize('source', ['naver_blog', 'naver_cafe'])
def test_naver_worker_defaults(tmp_path, source):
    run = worker._Run(tmp_path, 'S', 'list', [source], None, {})
    try:
        assert (run.limiters[source].concurrency, run.limiters[source].min_interval_s) == (1, 1)
    finally:
        run.close('stopped')


@pytest.mark.parametrize('error', [KeyError(), AttributeError(), IndexError()])
def test_parse_error_classification(tmp_path, error):
    run = worker._Run(tmp_path, 'S', 'list', ['youtube'], None, {})
    try:
        for _ in range(10):
            run.outcome('youtube', error)
        assert run.channels['youtube']['status'] == 'paused_parse_error'
    finally:
        run.close('stopped')


def test_youtube_kst_midnight():
    stamp = datetime(2026, 9, 28, 15, 1, tzinfo=timezone.utc).timestamp()
    assert _date({'timestamp': stamp}) == '2026-09-29'


def test_worker_passes_video_limit_to_search(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(YoutubeAdapter, '_extract', lambda self, url, **kw: calls.append(url) or {'entries': [{'id': str(i)} for i in range(30)]})
    run = worker._Run(tmp_path, 'S', 'list', ['youtube'], None, {'youtube': {'videos_per_keyword': 23}})
    try:
        run.q.add_list_tasks(worker._keywords(['keyword']), ['youtube'])
        jobs = run.q.next_list_tasks('youtube', 1)
        result = list(run.execute(jobs, {'youtube': YoutubeAdapter()}, 'list', threading.Event()))
        assert result[0][2] is None
        assert len(result[0][1].items) == 23
        assert calls == ['ytsearch23:keyword']
    finally:
        run.close('stopped')


def test_status_reports_naver_effective_interval(tmp_path, monkeypatch):
    from app.crawl import control
    from app.context import store
    monkeypatch.setattr(settings, 'local_data_dir', str(tmp_path))
    root = tmp_path / 'crawl/S/collections/c1'
    root.mkdir(parents=True)
    store.write_json(root / 'meta.json', {'keywords': []})
    store.write_json(root / 'manifest.json', {'channels': ['naver_blog', 'naver_cafe'], 'config': {}})
    assert control._status_settings({'sid': 'S', 'collectionId': 'c1'})['min_interval_s'] == {'naver_blog': 1, 'naver_cafe': 1}
