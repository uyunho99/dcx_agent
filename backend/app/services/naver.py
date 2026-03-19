import logging

import requests

from app.config import settings

logger = logging.getLogger(__name__)


def search_naver_cafe(query: str, display: int = 100, start: int = 1) -> dict | None:
    url = "https://openapi.naver.com/v1/search/cafearticle.json"
    headers = {
        "X-Naver-Client-Id": settings.naver_client_id,
        "X-Naver-Client-Secret": settings.naver_client_secret,
    }
    params = {"query": query, "display": display, "start": start, "sort": "date"}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            logger.error("Naver API HTTP %d: %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        if "errorMessage" in data:
            logger.error(
                "Naver API error: %s (code=%s)",
                data.get("errorMessage"),
                data.get("errorCode"),
            )
            return None
        return data
    except Exception as e:
        logger.error("Naver API request failed: %s", e)
        return None
