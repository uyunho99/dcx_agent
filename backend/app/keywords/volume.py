"""Attach monthly search volume without changing the supplied keywords."""

from datetime import date

from app.config import settings
from app.external import naver_searchad
from app.external.base import Unconnected
from app.keywords.models import Keyword


def today_iso() -> str:
    return date.today().isoformat()


def attach_volumes(kws: list[Keyword]) -> list[Keyword]:
    try:
        counts = naver_searchad.monthly_volume([kw.kw for kw in kws])
        source, at = 'searchad', today_iso()
    except Unconnected:
        counts = {}
        source, at = 'unconnected', None
    result = []
    for kw in kws:
        copied = kw.model_copy(deep=True)
        monthly = counts.get(kw.kw)
        copied.volume = {'monthly': monthly, 'source': source, 'at': at}
        copied.badges = [badge for badge in copied.badges if badge != 'low_volume']
        if monthly is not None and monthly < settings.low_volume_threshold:
            copied.badges.append('low_volume')
        result.append(copied)
    return result
