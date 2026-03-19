import logging
import time

import requests

from app.config import settings

logger = logging.getLogger(__name__)


def _total_to_score(total: int) -> int:
    """Map Naver cafe search total count to a 25-95 relevance score."""
    if total >= 10000:
        return 95
    elif total >= 5000:
        return 85
    elif total >= 1000:
        return 75
    elif total >= 500:
        return 65
    elif total >= 100:
        return 55
    elif total >= 50:
        return 45
    elif total >= 10:
        return 35
    return 25


def score_keyword(bk: str, kw: str) -> dict:
    """Score a single keyword via Naver Cafe search count."""
    score = 50
    total = 0
    try:
        resp = requests.get(
            "https://openapi.naver.com/v1/search/cafearticle.json",
            headers={
                "X-Naver-Client-Id": settings.naver_client_id,
                "X-Naver-Client-Secret": settings.naver_client_secret,
            },
            params={"query": f"{bk} {kw}", "display": 1},
            timeout=3,
        )
        total = resp.json().get("total", 0)
        score = _total_to_score(total)
    except Exception:
        pass
    return {"score": score, "total": total}


def score_keywords_batch(
    bk: str, keywords: list[dict], sleep_interval: float = 0.1
) -> list[dict]:
    """Score a batch of keywords. Each item must have 'kw' and 'cat' keys."""
    results = []
    for i, kw_obj in enumerate(keywords):
        kw = kw_obj.get("kw", "")
        cat = kw_obj.get("cat", "")
        s = score_keyword(bk, kw)
        results.append({"kw": kw, "cat": cat, "score": s["score"], "total": s["total"]})
        if i % 5 == 4:
            time.sleep(sleep_interval)
    return results


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
