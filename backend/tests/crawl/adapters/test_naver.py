"""Offline contracts for the D-094 keyless Naver adapters."""
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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


def adapter(cls, content, status=200, *, now=datetime(2026, 9, 29, 12)):
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(status, content=content)
    client = httpx.Client(transport=httpx.MockTransport(handle))
    return cls(client=client, sleep=lambda _: None,
               now=lambda: now), requests


def recorded_list(cls, number):
    manifest = json.loads(fixture(cls, 'manifest.json'))
    captured_at = datetime.fromisoformat(manifest['captured_at']).astimezone(ZoneInfo('Asia/Seoul'))
    a, _ = adapter(cls, fixture(cls, f'list-{number}.html'), now=captured_at)
    try:
        return a.list_page(manifest['keyword'], str(1 + (number - 1) * 30))
    finally:
        a.client.close()


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


@pytest.mark.parametrize('cls,number,relative_dates', [
    (NaverBlogAdapter, 1, {0: '2026-09-15', 19: '2026-09-26', 28: '2026-09-08'}),
    (NaverBlogAdapter, 2, {12: '2026-09-08', 25: '2026-09-28', 27: '2026-09-23'}),
    (NaverCafeAdapter, 1, {
        0: '2026-09-28', 1: '2026-09-22', 2: '2026-09-25',
        6: '2026-09-29', 24: '2026-09-26', 29: '2026-09-08',
    }),
    (NaverCafeAdapter, 2, {
        0: '2026-09-28', 1: '2026-09-22', 2: '2026-09-25',
        6: '2026-09-29', 24: '2026-09-26', 29: '2026-09-08',
    }),
])
def test_recorded_list_dates(cls, number, relative_dates):
    page = recorded_list(cls, number)
    assert len(page.items) == 30
    for entry in page.items:
        assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', entry.date or ''), entry.url
        assert datetime.strptime(entry.date, '%Y-%m-%d').date().isoformat() == entry.date
    # These expectations come from the recorded relative labels, with the clock
    # fixed to manifest captured_at in Naver's local timezone.
    for index, expected in relative_dates.items():
        assert page.items[index].date == expected, page.items[index].url


@pytest.mark.parametrize('number', [1, 2])
def test_recorded_cafe_list_names(number):
    page = recorded_list(NaverCafeAdapter, number)
    assert len(page.items) == 30
    for entry in page.items:
        name = entry.src_meta['cafe']
        assert name.strip(), entry.url
        assert not name.startswith('사용자'), (entry.url, name)


@pytest.mark.parametrize('number', [1, 2])
@pytest.mark.parametrize('detail_number,expected_date', [(1, '2026-09-28'), (2, '2026-09-22')])
def test_recorded_cafe_restricted_doc_keeps_list_date(number, detail_number, expected_date):
    entry = recorded_list(NaverCafeAdapter, number).items[detail_number - 1]
    manifest = json.loads(fixture(NaverCafeAdapter, 'manifest.json'))
    recording = next(r for r in manifest['requests'] if r['file'] == f'detail-{detail_number}.json')
    assert recording['status_code'] == 401
    a, requests = adapter(NaverCafeAdapter, fixture(NaverCafeAdapter, recording['file']),
                          recording['status_code'])
    try:
        doc, = a.fetch(entry)
        assert str(requests[0].url) == recording['url']
        assert doc.access == 'restricted'
        assert doc.date == entry.date == expected_date
    finally:
        a.client.close()


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
    assert a.list_page('keyword', '31').next_cursor is None  # Retry stays terminal.
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
        a._limiter.rng = lambda: 0.5
        a.list_page('keyword')
        a.fetch(item(cls))
    assert starts[1] - starts[0] == 0.5


@pytest.mark.parametrize('result', [
    {'errorCode': '0004'},
    {'reason': '등급'},
    {'errorCode': '9999', 'reason': '등급'},
])
def test_cafe_403_restriction_json_returns_snippet(result):
    a, _ = adapter(NaverCafeAdapter, json.dumps({'result': result}).encode(), 403)
    doc, = a.fetch(item(NaverCafeAdapter))
    assert (doc.title, doc.body, doc.access, doc.comments) == ('목록 제목', '검색 요약', 'restricted', [])


@pytest.mark.parametrize('content', [b'', b'<html>Forbidden</html>', b'{"result":{}}', b'[]'])
def test_cafe_403_without_restriction_is_blocked(content):
    a, _ = adapter(NaverCafeAdapter, content, 403)
    with pytest.raises(AdapterBlocked):
        a.fetch(item(NaverCafeAdapter))


def test_cafe_429_restriction_json_is_always_blocked():
    a, _ = adapter(NaverCafeAdapter, b'{"result":{"errorCode":"0004"}}', 429)
    with pytest.raises(AdapterBlocked):
        a.fetch(item(NaverCafeAdapter))


@pytest.mark.parametrize('content', [b'', b'<html>Login required</html>', b'{"result":null}'])
def test_cafe_401_without_json_article_returns_snippet(content):
    a, _ = adapter(NaverCafeAdapter, content, 401)
    doc, = a.fetch(item(NaverCafeAdapter))
    assert doc.body == '검색 요약' and doc.access == 'restricted'


def search_rows(*urls):
    from html import escape
    return ('<ul class="lst_view">' + ''.join(
        f'<li><a class="title_link" href="{escape(url)}">Article title</a>'
        '<a class="dsc_link">Snippet</a></li>' for url in urls) + '</ul>').encode()


@pytest.mark.parametrize('cls,url,canonical', [
    (NaverBlogAdapter, 'https://blog.naver.com/PostView.naver?blogId=user_a&logNo=123&tracking=1',
     'https://blog.naver.com/user_a/123'),
    (NaverCafeAdapter, 'https://m.cafe.naver.com/ca-fe/cafes/123/articles/456?tracking=1',
     'https://cafe.naver.com/ca-fe/cafes/123/articles/456'),
])
def test_alternate_article_urls_normalized_and_non_articles_skipped(cls, url, canonical):
    a, _ = adapter(cls, search_rows('https://example.com/ad', url, '#more', canonical))
    page = a.list_page('keyword')
    assert [i.url for i in page.items] == [canonical]
    assert page.items[0].title == 'Article title'


def test_cafe_numeric_id_url_fetch_uses_cafe_id():
    a, requests = adapter(NaverCafeAdapter, fixture(NaverCafeAdapter, 'detail-3.json'))
    numeric = ListItem('https://cafe.naver.com/ca-fe/cafes/123/articles/456', 'title', 'snippet', None, {})
    assert a.fetch(numeric)[0].access == 'public'
    assert str(requests[0].url) == 'https://article.cafe.naver.com/gw/v4/cafes/123/articles/456?useCafeId=true'


@pytest.mark.parametrize('cls', CLASSES)
def test_non_article_results_raise_even_with_no_results_notice(cls):
    a, _ = adapter(cls, search_rows('https://example.com/ad') +
                   '<div class="not_found">검색결과가 없습니다.</div>'.encode())
    with pytest.raises(ValueError):
        a.list_page('keyword')


@pytest.mark.parametrize('cls', CLASSES)
@pytest.mark.parametrize('link', ['<a class="title_link">Title</a>', '<a class="title_link" href="#more"></a>'])
def test_result_missing_href_or_title_raises(cls, link):
    a, _ = adapter(cls, (f'<ul class="lst_view"><li>{link}</li></ul>').encode() +
                   search_rows(item(cls).url))
    with pytest.raises(ValueError):
        a.list_page('keyword')


def test_page_signature_storage_is_bounded():
    def handle(request):
        start = int(request.url.params['start'])
        return httpx.Response(200, content=search_rows(*(
            f'https://blog.naver.com/user_a/{i}' for i in range(start, start + 30))))
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        a = NaverBlogAdapter(client, sleep=lambda _: None)
        for start in range(1, 301, 30):
            assert a.list_page('same keyword', str(start)).next_cursor == str(start + 30)
        assert len(a._pages) == 1
        for number in range(300):
            a.list_page(f'keyword {number}')
        assert len(a._pages) <= 256
        assert a.list_page('keyword 299', '1').next_cursor == '31'


@pytest.mark.parametrize('code', ['9999', 'GRADE_403'])
def test_cafe_403_unknown_error_code_is_blocked(code):
    payload = {'result': {'errorCode': code, 'message': 'too many requests'}}
    a, _ = adapter(NaverCafeAdapter, json.dumps(payload).encode(), 403)
    with pytest.raises(AdapterBlocked):
        a.fetch(item(NaverCafeAdapter))
