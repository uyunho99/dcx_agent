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
