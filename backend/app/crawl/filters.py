"""P2 first-match rule filters; no adapter dependency or network access."""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Mapping

# Existing crawling UI defaults, in their original order (service has no literal ad list).
DEFAULT_AD_WORDS = [
    '협찬', '광고', '제공받', '원고료', '체험단', '서포터즈', '중고', '판매', '거래',
    '체험단', '협찬', '원고료', '소정의', '제공받아', '서포터즈',
]
DEFAULT_EXCLUDE_SOURCES = [
    "중고나라", "번개장터", "당근", "세컨웨어", "헬로마켓", "중고", "장터",
    "부동산", "판매", "팝니다", "삽니다", "택배", "무료배송", "할인코드",
    "쿠폰", "홍보", "광고", "업체", "시공", "인테리어업체", "이사", "용달",
    "대출", "보험설계사", "설계사모집", "모집",
]


@dataclass
class FilterConfig:
    date_from: str | date | None = field(default_factory=lambda: date.today() - timedelta(days=365))
    date_to: str | date | None = field(default_factory=date.today)
    ad_words: list[str] = field(default_factory=lambda: DEFAULT_AD_WORDS.copy())
    exclude_sources: list[str] = field(default_factory=lambda: DEFAULT_EXCLUDE_SOURCES.copy())
    include_sources: list[str] = field(default_factory=list)
    product_name_filter: bool = False
    bk: str = ''


def _get(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, Mapping) else getattr(obj, key, default)


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _contains(text, words):
    return any(word and word.casefold() in text for word in words)


def _check(item, cfg, detail):
    d, start, end = _date(_get(item, 'date')), _date(cfg.date_from), _date(cfg.date_to)
    if d and ((start and d < start) or (end and d > end)):
        return '①'
    text = f"{_get(item, 'title', '') or ''} {_get(item, 'body' if detail else 'snippet', '') or ''}".casefold()
    if _contains(text, cfg.ad_words):
        return '②'
    if not detail:
        meta = _get(item, 'src_meta', {}) or {}
        # Match source identity only, never arbitrary metadata or article content.
        keys = ('cafe_name', 'cafename', 'cafe', 'cafe_id', 'cafe_url', 'blog_id', 'blog_name',
                'bloggername', 'bloggerlink', 'board', 'board_id', 'board_name',
                'channel_id', 'channel_name')
        identities = [str(_get(item, 'source', '') or '')]
        identities.extend(str(meta[k]) for k in keys if meta.get(k) is not None)
        source = ' '.join(identities).casefold()
        if _contains(source, cfg.exclude_sources):
            return '③'
        if cfg.include_sources and not _contains(source, cfg.include_sources):
            return '④'
    if cfg.product_name_filter and cfg.bk.casefold() not in text:
        return '⑤'
    return None


def check_list(item: Any, cfg: FilterConfig) -> str | None:
    return _check(item, cfg, detail=False)


def check_doc(doc: Any, cfg: FilterConfig) -> str | None:
    return _check(doc, cfg, detail=True)
