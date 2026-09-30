import hashlib

import pytest

from app.crawl.urls import doc_id, normalize_url


def test_normalize_url_collapses_cafe_variants():
    expected = "https://cafe.naver.com/mamcafe/123"
    for url in (
        "https://m.cafe.naver.com/ca-fe/mamcafe/123?art=xx",
        "https://m.cafe.naver.com/mamcafe/123/",
        expected,
    ):
        assert normalize_url(url, "naver_cafe") == expected


def test_strips_tracking_params():
    url = "HTTPS://CAFE.NAVER.COM/ArticleRead.nhn/?utm_source=x&utm_medium=y&fbclid=z&gclid=x&art=x&query=x&where=x&sm=x&clubid=2&articleid=1#fragment"
    expected = "https://cafe.naver.com/ArticleRead.nhn?articleid=1&clubid=2"
    assert normalize_url(url, "naver_cafe") == expected


@pytest.mark.parametrize("path", [
    "/ca-fe/cafes/123/articles/456", "/ca-fe/mamcafe/not-numeric",
    "/ca-fe/mamcafe", "/ca-fe/mamcafe/123/extra",
])
def test_normalize_url_preserves_other_ca_fe_paths(path):
    assert normalize_url("https://m.cafe.naver.com" + path + "/?utm_source=x#fragment", "naver_cafe") == "https://cafe.naver.com" + path


@pytest.mark.parametrize("source", ["naver_cafe", "naver_blog", "youtube", "ppomppu", "clien", "fixture"])
def test_naver_trackers_are_source_scoped(source):
    url = "https://example.com/post?art=x&query=x&where=x&sm=x&utm_source=x&FBCLID=x&gclid=x"
    expected = "https://example.com/post"
    if source not in {"naver_cafe", "naver_blog"}:
        expected += "?art=x&query=x&sm=x&where=x"
    assert normalize_url(url, source) == expected


@pytest.mark.parametrize("url", [
    "https://youtu.be/ID?si=abc",
    "https://youtu.be/ID?si=abc&feature=share&t=10&pp=abc&utm_source=x&fbclid=x&gclid=x",
    "https://m.youtube.com/watch?v=ID&SI=abc&FEATURE=share&T=10&PP=abc",
])
def test_youtube_trackers_are_removed(url):
    assert normalize_url(url, "youtube") == "https://www.youtube.com/watch?v=ID"


@pytest.mark.parametrize("source", ["naver_cafe", "naver_blog", "ppomppu", "clien", "fixture"])
def test_youtube_trackers_are_preserved_for_other_sources(source):
    url = "https://example.com/post?si=abc&feature=share&t=10&pp=abc"
    assert normalize_url(url, source) == "https://example.com/post?feature=share&pp=abc&si=abc&t=10"


@pytest.mark.parametrize("source,prefix", [
    ("naver_cafe", "nc"), ("naver_blog", "nb"), ("youtube", "yt"),
    ("ppomppu", "pp"), ("clien", "cl"), ("fixture", "fx"),
])
def test_doc_id_deterministic_and_prefixed(source, prefix):
    url = "https://example.com/post/1"
    expected = prefix + "_" + hashlib.sha1((url + "thread-1").encode()).hexdigest()[:16]
    assert doc_id(source, url, "thread-1") == expected
    assert doc_id(source, url, "thread-1") == doc_id(source, url, "thread-1")
    assert doc_id(source, url, "thread-2") != expected
    assert doc_id(source, url) == prefix + "_" + hashlib.sha1(url.encode()).hexdigest()[:16]


def test_normalize_url_collapses_blog_variants():
    expected = "https://blog.naver.com/writer/123"
    assert normalize_url("http://m.blog.naver.com/writer/123/?utm_source=x", "naver_blog") == expected
    assert normalize_url(expected, "naver_blog") == expected


def test_normalize_url_collapses_youtube_variants():
    expected = "https://www.youtube.com/watch?v=AbC_123"
    for url in (
        "https://youtu.be/AbC_123?utm_source=x",
        "http://m.youtube.com/watch?v=AbC_123#fragment",
        expected,
    ):
        assert normalize_url(url, "youtube") == expected


def test_normalize_url_preserves_and_sorts_content_params():
    url = "HTTPS://EXAMPLE.COM/Post/?z=2&a=2&a=1&empty=#fragment"
    expected = "https://example.com/Post?a=1&a=2&empty=&z=2"
    assert normalize_url(url, "fixture") == expected
    assert normalize_url(expected, "fixture") == expected
