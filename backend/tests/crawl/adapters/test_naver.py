"""Offline contracts for the D-094 keyless Naver adapters."""
import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from selectolax.parser import HTMLParser

from app.crawl.adapters import REGISTRY
from app.crawl.adapters.base import AdapterBlocked, ListItem
from app.crawl.adapters.naver_blog import NaverBlogAdapter
from app.crawl.adapters.naver_cafe import NaverCafeAdapter

FIXTURES = Path(__file__).parents[2] / 'fixtures/http'
CLASSES = [NaverBlogAdapter, NaverCafeAdapter]


def fixture(cls, name):
    return (FIXTURES / cls.source / name).read_bytes()


def adapter(cls, content, status=200):
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(status, content=content)
    client = httpx.Client(transport=httpx.MockTransport(handle))
    return cls(client=client, sleep=lambda _: None,
               now=lambda: datetime(2026, 9, 29, 12)), requests


def item(cls):
    path = 'user_a/224406855054' if cls is NaverBlogAdapter else 'bongo312/317927'
    kind = cls.source.split('_')[1]
    return ListItem(f'https://{kind}.naver.com/{path}', '목록 제목', '검색 요약', '2026-09-25', {})


def check_list(cls):
    a, requests = adapter(cls, fixture(cls, 'list-1.html'))
    page = a.list_page('에어컨 소음', None)
    assert len(page.items) == 30
    assert page.next_cursor == '31'
    assert all(i.title and i.snippet and i.src_meta for i in page.items)
    assert len({i.url for i in page.items}) == 30
    assert all('?' not in i.url for i in page.items)
    assert requests[0].url.params['start'] == '1'
    a2, requests2 = adapter(cls, fixture(cls, 'list-2.html'))
    second = a2.list_page('에어컨 소음', page.next_cursor)
    assert len(second.items) == 30 and second.next_cursor == '61'
    assert requests2[0].url.params['start'] == '31'
    if cls is NaverBlogAdapter:
        assert not {i.url for i in page.items} & {i.url for i in second.items}


def test_cafe_list_parses_items_and_cursor():
    check_list(NaverCafeAdapter)


def test_blog_list_parses_items_and_cursor():
    check_list(NaverBlogAdapter)


@pytest.mark.parametrize('cls', CLASSES)
def test_search_uses_keyword_only_query(cls):
    a, requests = adapter(cls, fixture(cls, 'list-1.html'))
    kw = ' 에어컨 + 소음 & 한글 '
    a.list_page(kw)
    assert requests[0].url.params['query'] == kw
    assert dict(requests[0].url.params) == {'ssc': f'tab.{cls.source.split("_")[1]}.all', 'query': kw, 'start': '1'}
    assert requests[0].url.host == 'search.naver.com'
    assert 'Mozilla' in requests[0].headers['User-Agent']
    assert a.is_available()
    a.close()
    assert not a.client.is_closed
    a.client.close()


@pytest.mark.parametrize('cls', CLASSES)
def test_list_termination_and_parse_failure(cls):
    tree = HTMLParser(fixture(cls, 'list-1.html'))
    rows = tree.css('[data-template-id="ugcItem"]' if cls is NaverBlogAdapter else '.lst_view > li')
    for row in rows[1:]:
        row.decompose()
    a, _ = adapter(cls, tree.html.encode())
    assert len(a.list_page('키워드').items) == 1
    assert a.list_page('키워드').next_cursor is None
    a, _ = adapter(cls, '<div class="not_found">검색결과가 없습니다.</div>'.encode())
    assert a.list_page('없음').items == []
    a, _ = adapter(cls, b'<html>changed layout</html>')
    with pytest.raises(ValueError):
        a.list_page('키워드')


@pytest.mark.parametrize('cls', CLASSES)
@pytest.mark.parametrize('status', [403, 429])
def test_http_403_raises_blocked(cls, status):
    a, _ = adapter(cls, b'', status)
    with pytest.raises(AdapterBlocked):
        a.list_page('keyword')
    with pytest.raises(AdapterBlocked):
        a.fetch(item(cls))


def test_cafe_detail_body_and_nested_comments():
    cls = NaverCafeAdapter
    payload = json.loads(fixture(cls, 'detail-3.json'))
    payload['result']['comments']['items'].append(dict(payload['result']['comments']['items'][0], isDeleted=True, content='DELETED'))
    a, requests = adapter(cls, json.dumps(payload).encode())
    doc, = a.fetch(item(cls))
    assert '포터2' in doc.body and '<div' not in doc.body
    assert {c.depth for c in doc.comments} == {0, 1}
    assert all(c.author_hash and len(c.date) == 10 for c in doc.comments)
    assert not any(c.text == 'DELETED' for c in doc.comments)
    assert doc.access == 'public' and doc.author_raw
    assert doc.date == '2026-09-25'
    assert str(requests[0].url) == 'https://article.cafe.naver.com/gw/v4/cafes/bongo312/articles/317927?useCafeId=false'
    assert requests[0].headers['Referer'] == 'https://m.cafe.naver.com/'
    assert len(requests) == 1
    assert len(a.fetch(item(cls), max_comments=1)[0].comments) == 1


def test_cafe_restricted_page():
    a, _ = adapter(NaverCafeAdapter, fixture(NaverCafeAdapter, 'detail-1.json'), 401)
    doc, = a.fetch(item(NaverCafeAdapter))
    assert (doc.title, doc.body, doc.access, doc.comments) == ('목록 제목', '검색 요약', 'restricted', [])


@pytest.mark.parametrize('number', [1, 2, 3])
def test_blog_detail_body_no_comments(number):
    a, requests = adapter(NaverBlogAdapter, fixture(NaverBlogAdapter, f'detail-{number}.html'))
    doc, = a.fetch(item(NaverBlogAdapter))
    assert len(doc.body) > 100 and '<script' not in doc.body
    assert doc.comments == [] and doc.access == 'public'
    assert isinstance(doc.src_meta['comment_count'], int)
    assert len(doc.date) == 10
    assert str(requests[0].url) == 'https://m.blog.naver.com/user_a/224406855054'
    assert len(requests) == 1


@pytest.mark.parametrize('markup', ['<div id="postViewArea">옛 본문</div>', '<div class="se_component">옛 본문</div>'])
def test_blog_older_layouts(markup):
    a, _ = adapter(NaverBlogAdapter, markup.encode())
    assert a.fetch(item(NaverBlogAdapter))[0].body == '옛 본문'


@pytest.mark.parametrize('cls,content', [(NaverBlogAdapter, b'<html>shell</html>'), (NaverCafeAdapter, b'{"result":{}}')])
def test_detail_parse_failure_raises_value_error(cls, content):
    a, _ = adapter(cls, content)
    with pytest.raises(ValueError):
        a.fetch(item(cls))


@pytest.mark.parametrize('value,expected', [('3일 전', '2026-09-26'), ('2시간 전', '2026-09-29'), ('2026. 9. 2.', '2026-09-02'), ('2026.09.20.', '2026-09-20')])
def test_date_normalization(value, expected):
    a, _ = adapter(NaverBlogAdapter, b'')
    assert a.normalize_date(value) == expected


def test_registration():
    for cls in CLASSES:
        a = REGISTRY[cls.source]()
        try:
            assert isinstance(a, cls) and a.is_available()
        finally:
            a.close()


@pytest.mark.parametrize('cls', CLASSES)
def test_repeated_full_page_terminates(cls):
    a, _ = adapter(cls, fixture(cls, 'list-1.html'))
    assert a.list_page('keyword').next_cursor == '31'
    assert a.list_page('keyword', '31').next_cursor is None
    assert a.list_page('other keyword').next_cursor == '31'


@pytest.mark.parametrize('cls', CLASSES)
def test_list_extracts_relative_date(cls):
    tree = HTMLParser(fixture(cls, 'list-1.html'))
    node = tree.css_first('.sds-comps-profile-info-subtext' if cls is NaverBlogAdapter else '.user_info .sub')
    replacement = HTMLParser('<span class="date">3일 전</span>')
    node.replace_with(replacement.css_first('span'))
    a, _ = adapter(cls, tree.html.encode())
    assert a.list_page('keyword').items[0].date == '2026-09-26'


@pytest.mark.parametrize('status', [200, 401])
def test_cafe_grade_restricted(status):
    payload = {'result': {'errorCode': 'AUTH_GRADE', 'reason': '멤버 등급이 낮아 읽기 권한이 없습니다.'}}
    a, _ = adapter(NaverCafeAdapter, json.dumps(payload).encode(), status)
    assert a.fetch(item(NaverCafeAdapter))[0].access == 'restricted'


@pytest.mark.parametrize('cls', CLASSES)
def test_malformed_result_is_not_silently_skipped(cls):
    tree = HTMLParser(fixture(cls, 'list-1.html'))
    node = tree.css_first('.sds-comps-text-type-headline1' if cls is NaverBlogAdapter else '.title_link')
    (node.parent if cls is NaverBlogAdapter else node).decompose()
    a, _ = adapter(cls, tree.html.encode())
    with pytest.raises(ValueError):
        a.list_page('keyword')


@pytest.mark.parametrize('cls', CLASSES)
def test_request_interval_shared_between_list_and_detail(cls):
    ticks = [0.0]
    starts = []
    def sleep(seconds):
        ticks[0] += seconds
    def handle(request):
        starts.append(ticks[0])
        if request.url.host == 'search.naver.com':
            content = fixture(cls, 'list-1.html')
        else:
            content = fixture(cls, 'detail-1.html' if cls is NaverBlogAdapter else 'detail-3.json')
        return httpx.Response(200, content=content)
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        a = cls(client, clock=lambda: ticks[0], sleep=sleep)
        a.list_page('keyword')
        a.fetch(item(cls))
    assert starts[1] - starts[0] >= 1.0
