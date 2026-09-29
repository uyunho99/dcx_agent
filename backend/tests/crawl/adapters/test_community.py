"""Offline contract tests against the committed, masked HTTP captures."""
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.config import settings
from app.crawl.adapters.base import AdapterBlocked
from app.crawl.adapters.clien import ClienAdapter
from app.crawl.adapters.ppomppu import PpomppuAdapter
from app.crawl.hashing import author_hash

FIXTURES = Path(__file__).parents[2] / "fixtures" / "http"
CLASSES = {"clien": ClienAdapter, "ppomppu": PpomppuAdapter}


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.delays = []

    def __call__(self):
        return self.now

    def sleep(self, delay):
        self.delays.append(delay)
        self.now += delay


@pytest.fixture(autouse=True)
def salt(tmp_path, monkeypatch):
    path = tmp_path / "author-salt"
    path.write_text("a" * 64)
    monkeypatch.setattr(settings, "author_salt_path", str(path))


def adapter(site, transform=None):
    root = FIXTURES / site
    manifest = json.loads((root / "manifest.json").read_text())
    requests = []
    clock = FakeClock()

    def respond(request):
        requests.append((request, clock()))
        url = urlsplit(str(request.url))
        for capture in manifest["requests"]:
            expected = urlsplit(capture["url"])
            if url.path == expected.path and (
                capture["file"] == "list.html"
                or parse_qs(url.query).get("no") == parse_qs(expected.query).get("no")
            ):
                content = (root / capture["file"]).read_bytes()
                if transform:
                    content = transform(capture["file"], content)
                # Deliberately wrong HTTP charset: site-specific decoding wins.
                return httpx.Response(200, content=content, headers={"Content-Type": "text/html; charset=iso-8859-1"})
        raise AssertionError(f"Unrecorded request: {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(respond))
    return CLASSES[site](client=client, clock=clock, sleep=clock.sleep), requests, clock, manifest


def check_list(site):
    a, requests, _, manifest = adapter(site)
    page = a.list_page(manifest["keyword"], None)
    assert len(page.items) >= 3
    assert [i.url for i in page.items[:3]] == [r["url"] for r in manifest["requests"][1:]]
    assert len({i.url for i in page.items}) == len(page.items)
    first = page.items[0]
    assert first.title == ("에어팟 5 무선충전 케이스 모델 후기" if site == "clien" else "전에 살던월세집 세입자를 우연하게 봤는데 개고생하겠다.")
    assert "에어컨" in first.snippet
    assert first.date.startswith("2026-09")
    assert page.next_cursor == ("1" if site == "clien" else None)
    assert a.is_available()
    request = requests[0][0]
    assert "Mozilla/" in request.headers["User-Agent"]
    assert request.headers["Accept-Language"].startswith("ko-KR")
    if site == "ppomppu":
        assert request.headers["Referer"].startswith("https://www.ppomppu.co.kr/")
    assert str(request.url) == manifest["requests"][0]["url"]


def test_clien_list_parse():
    check_list("clien")


def test_ppomppu_list_parse():
    check_list("ppomppu")


@pytest.mark.parametrize("index,body,count,author", [
    (0, "1줄 요약: 어지간하면 에어팟 프로 3 사세요.", 16, "사용자A"),
    (1, "냉매", 32, "사용자B"),
    (2, "질문이 하나 있는데 전기차 휀다 방음", 21, "사용자C"),
])
def test_clien_detail_body_comments(index, body, count, author):
    a, _, _, manifest = adapter("clien")
    item = a.list_page(manifest["keyword"], None).items[index]
    doc, = a.fetch(item)
    assert body in doc.body
    assert "닉네임 신고" not in doc.body
    assert doc.title == item.title
    assert doc.author_raw == author
    assert doc.access == "public" and doc.date.startswith("2026-09")
    assert len(doc.comments) == count
    assert any(c.depth == 1 for c in doc.comments)
    assert all(c.text and c.date and len(c.author_hash) == 16 for c in doc.comments)
    if index == 0:
        assert "전 귀가 이상하게 생겨서" in doc.comments[0].text
        assert doc.src_meta["comment_threads"][2] == {"id": "152452488", "parent": "152448786"}


@pytest.mark.parametrize("index,body,count,author,comment", [
    (0, "우선 안쪽이라 소음안녕", 3, "사용자O", "많이 예뻐요?"),
    (1, "창문닫고 선풍기 틀고있네요", 2, "사용자R", "에어컨필수"),
    (2, "창문닫고 선풍기 틀고있네요", 1, "사용자R", "어디시길래? 서울 문열면 추워요"),
])
def test_ppomppu_detail_body_comments(index, body, count, author, comment):
    a, _, _, manifest = adapter("ppomppu")
    item = a.list_page(manifest["keyword"], None).items[index]
    doc, = a.fetch(item)
    assert body in doc.body
    assert "개인정보처리방침" not in doc.body
    assert doc.title == item.title
    assert doc.author_raw == author
    assert doc.access == "public" and doc.date.startswith("2026-09")
    assert len(doc.comments) == count
    assert doc.comments[0].text == comment
    assert all(c.depth == 0 and c.date and len(c.author_hash) == 16 for c in doc.comments)
    if index == 0:
        assert doc.comments[0].author_hash == author_hash("ppomppu", "사용자M")


def check_encoding(site):
    a, requests, _, manifest = adapter(site)
    page = a.list_page(manifest["keyword"], None)
    for index, item in enumerate(page.items[:3]):
        doc, = a.fetch(item)
        expected = ["에어컨", "냉매", "전기차"] if site == "clien" else ["에어컨"] * 3
        assert expected[index] in doc.body
        assert "\ufffd" not in doc.body + doc.title + "".join(c.text for c in doc.comments)
    raw_query = urlsplit(str(requests[0][0].url)).query
    query = parse_qs(raw_query, encoding="euc-kr" if site == "ppomppu" else "utf-8")
    assert query["keyword" if site == "ppomppu" else "q"] == [manifest["keyword"]]


def test_clien_encoding():
    check_encoding("clien")


def test_ppomppu_encoding():
    check_encoding("ppomppu")


@pytest.mark.parametrize("site", CLASSES)
def test_min_interval_enforced(site):
    a, requests, clock, manifest = adapter(site)
    page = a.list_page(manifest["keyword"], None)
    a.fetch(page.items[0])
    a.list_page(manifest["keyword"], None)
    assert [when for _, when in requests] == [0, 1, 2]
    assert clock.delays == [1, 1]


@pytest.mark.parametrize("site", CLASSES)
@pytest.mark.parametrize("status", [403, 429])
@pytest.mark.parametrize("operation", ["list", "fetch"])
def test_blocked_no_retry(site, status, operation):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(status)
    a, _, _, manifest = adapter(site)
    item = a.list_page(manifest["keyword"], None).items[0]
    a.client = httpx.Client(transport=httpx.MockTransport(respond))
    with pytest.raises(AdapterBlocked):
        if operation == "list":
            a.list_page(manifest["keyword"], None)
        else:
            a.fetch(item)
    assert len(calls) == 1


@pytest.mark.parametrize("site,param,cursor", [("clien", "p", "1"), ("ppomppu", "page", "2")])
def test_pagination(site, param, cursor):
    def transform(name, content):
        if site == "ppomppu" and name == "list.html":
            return content + b'<a href="/search_bbs.php?keyword=x&amp;page=2">2</a>'
        return content
    a, requests, _, manifest = adapter(site, transform)
    page = a.list_page(manifest["keyword"], None)
    assert page.next_cursor == cursor
    a.list_page(manifest["keyword"], page.next_cursor)
    assert parse_qs(urlsplit(str(requests[-1][0].url)).query)[param] == [cursor]


def test_ppomppu_reply_structure_and_rendered_comments():
    def transform(name, content):
        if name != "detail-1.html":
            return content
        # Supplement real captures (all their initial comments are roots).
        content = content.replace(b'"no":2682217,"c0":0,"c1":0,"depth":0,"parent":0',
                                  b'"no":2682217,"c0":0,"c1":0,"depth":1,"parent":2681812')
        return content + b'''<div id="comment_999" data-parent="2682217" data-depth="2">
            <span class="comment-name">user_a</span>
            <span class="comment-date">2026-09-17 14:00</span>
            <div class="comment-content">Rendered reply</div></div>'''
    a, _, _, manifest = adapter("ppomppu", transform)
    doc, = a.fetch(a.list_page(manifest["keyword"], None).items[0])
    assert [c.depth for c in doc.comments] == [0, 1, 0, 2]
    assert doc.src_meta["comment_threads"][1] == {"id": "2682217", "parent": "2681812"}
    assert doc.comments[-1].text == "Rendered reply"
    assert doc.src_meta["comment_threads"][-1] == {"id": "999", "parent": "2682217"}
