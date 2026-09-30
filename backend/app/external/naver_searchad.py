"""SearchAd keyword tool with injectable HTTP and no credential logging."""

import base64
import hashlib
import hmac
import time

import httpx

from app.config import settings
from app.external.base import LAST_ERRORS, Unconnected, configured
from app.keywords.normalize import norm_key

client_factory = httpx.Client
# Estimate each censored '< 10' side as 4 so both sides total at most 8 < 10.
LOW_COUNT_ESTIMATE = 4
_URI = '/keywordstool'


def timestamp_ms() -> str:
    return str(int(time.time() * 1000))


def _count(value: int | str) -> int:
    return LOW_COUNT_ESTIMATE if str(value).strip() == '< 10' else int(value)


def related_queries(hints: list[str], client: httpx.Client | None = None) -> list[tuple[str, int]]:
    """Fetch batches of five hints; return each related query once, in API order.

    Repeated results across batches use the latest monthly count, never a sum.
    HTTP/data errors propagate so a failed request is not mistaken for zero demand.
    """
    if not all(configured(name) for name in
               ('SEARCHAD_API_KEY', 'SEARCHAD_SECRET', 'SEARCHAD_CUSTOMER_ID')):
        raise Unconnected('naver_searchad')
    if not hints:
        return []
    owned = client is None
    client = client or client_factory()
    result: dict[str, int] = {}
    try:
        for start in range(0, len(hints), 5):
            timestamp = timestamp_ms()
            signature = base64.b64encode(hmac.new(
                settings.searchad_secret.encode(),
                f'{timestamp}.GET.{_URI}'.encode(), hashlib.sha256,
            ).digest()).decode()
            response = client.get(
                f'https://api.searchad.naver.com{_URI}',
                params={'hintKeywords': ','.join(hints[start:start + 5]), 'showDetail': '1'},
                headers={'X-Timestamp': timestamp, 'X-API-KEY': settings.searchad_api_key,
                         'X-Customer': settings.searchad_customer_id, 'X-Signature': signature},
                timeout=15,
            )
            response.raise_for_status()
            for item in response.json()['keywordList']:
                result[item['relKeyword']] = _count(item['monthlyPcQcCnt']) + _count(item['monthlyMobileQcCnt'])
        LAST_ERRORS.pop('naver_searchad', None)
        return list(result.items())
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        LAST_ERRORS['naver_searchad'] = 'request_failed'
        raise
    finally:
        if owned:
            client.close()


def monthly_volume(kws: list[str], client: httpx.Client | None = None) -> dict[str, int]:
    """Map returned counts to original input strings; omit absent API results."""
    counts = {norm_key(query): count for query, count in related_queries(kws, client=client)}
    return {kw: counts[norm_key(kw)] for kw in kws if norm_key(kw) in counts}
