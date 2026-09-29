from types import SimpleNamespace

from app.crawl.filters import FilterConfig, check_list, check_doc, DEFAULT_AD_WORDS, DEFAULT_EXCLUDE_SOURCES


def item(**kw):
    fields = dict(title='사용 후기', body='시원해요', snippet='시원해요', date='2026-06-01', src_meta={}, source='naver_blog')
    return SimpleNamespace(**(fields | kw))


def cfg(**kw):
    return FilterConfig(**(dict(date_from='2026-01-01', date_to='2026-12-31') | kw))


def test_product_filter_off_by_default():
    assert check_doc(item(), cfg(bk='에어컨')) is None
    assert check_list(item(), cfg(bk='에어컨')) is None


def test_product_filter_on_uses_body():
    c = cfg(product_name_filter=True, bk='에어컨')
    assert check_doc(item(body='에어컨 좋아요'), c) is None
    assert check_doc(item(), c) == '⑤'
    assert check_list(item(snippet='에어컨 좋아요'), c) is None
    assert check_list(item(), c) == '⑤'


def test_ad_words_blog_sponsored():
    assert check_doc(item(body='소정의 원고료를 받았습니다'), cfg()) == '②'
    assert check_list(item(snippet='소정의 원고료를 받았습니다'), cfg()) == '②'
    for word in ('체험단', '협찬', '원고료', '소정의', '제공받아', '서포터즈'):
        assert word in DEFAULT_AD_WORDS
    assert DEFAULT_EXCLUDE_SOURCES[0] == '중고나라'


def test_date_range():
    for check in (check_doc, check_list):
        for date in ('2025-12-31', '2027-01-01'):
            assert check(item(date=date), cfg()) == '①'
        for date in ('2026-01-01', '20261231', None, '', 'unknown', '2026-12-31T23:59:59+09:00'):
            assert check(item(date=date), cfg()) is None
    assert check_doc(item(date='2025-01-01', body='협찬'), cfg()) == '①'


def test_source_rules_and_first_match():
    c = cfg(include_sources=['리뷰카페'])
    assert check_list(item(src_meta={'cafe_name': '중고나라'}), c) == '③'
    assert check_list(item(src_meta={'cafe_name': '다른 카페'}), c) == '④'
    assert check_list(item(src_meta={'cafe_name': '리뷰카페'}), c) is None
    assert check_list(item(src_meta={'blog_id': '중고나라'}, snippet='광고'), c) == '②'
    assert check_doc(item(src_meta={'cafe_name': '중고나라'}), c) is None
    assert check_list(item(src_meta={'unrelated': '중고나라'}), cfg()) is None
