import httpx
from app.config import settings
from app.external.base import Unconnected, configured, LAST_ERRORS

client_factory = httpx.Client


def search_categories(bk, n=40, client: httpx.Client | None = None) -> list[tuple[str, str, str]]:
    if not all(configured(key) for key in ('NAVER_CLIENT_ID', 'NAVER_CLIENT_SECRET')):
        raise Unconnected('naver_shopping')
    owned = client is None
    client = client or client_factory()
    try:
        response = client.get('https://openapi.naver.com/v1/search/shop.json',
                              params={'query': bk, 'display': min(100, max(1, n))},
                              headers={'X-Naver-Client-Id': settings.naver_client_id,
                                       'X-Naver-Client-Secret': settings.naver_client_secret}, timeout=15)
        response.raise_for_status()
        result = [tuple(item.get(f'category{i}', '') for i in range(1, 4)) for item in response.json().get('items', [])]
        LAST_ERRORS.pop('naver_shopping', None)
        return [path for path in result if path[0]]
    except (httpx.HTTPError, ValueError, TypeError):
        LAST_ERRORS['naver_shopping'] = 'request_failed'
        return []
    finally:
        if owned:
            client.close()
