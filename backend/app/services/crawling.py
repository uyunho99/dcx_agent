import time
import json
import logging
from datetime import datetime, datetime as dt

from app.services.naver import search_naver_cafe
from app.services.s3 import save_jsonl
from app.utils.text import clean_text
from app.config import settings
from app.jobs.manager import job_manager

logger = logging.getLogger(__name__)


def crawl_keywords(config: dict) -> int:
    sid = config.get("sid", "s0")
    bk = config.get("bk", "")
    keywords = config.get("keywords", [])
    target = config.get("target", 50000)
    ad_filter = config.get("adFilter", [])
    cafes_filter = config.get("cafes", [])
    exclude_cafes = config.get("excludeCafes", [])

    if isinstance(ad_filter, str):
        ad_filter = [x.strip() for x in ad_filter.split(",") if x.strip()] if ad_filter else []
    if isinstance(cafes_filter, str):
        cafes_filter = [x.strip() for x in cafes_filter.split(",") if x.strip()] if cafes_filter else []
    if isinstance(exclude_cafes, str):
        exclude_cafes = [x.strip() for x in exclude_cafes.split(",") if x.strip()] if exclude_cafes else []

    date_from, date_to = config.get("dateFrom", ""), config.get("dateTo", "")
    results, total = [], 0

    default_exclude = [
        "중고나라", "번개장터", "당근", "세컨웨어", "헬로마켓", "중고", "장터",
        "부동산", "판매", "팝니다", "삽니다", "택배", "무료배송", "할인코드",
        "쿠폰", "홍보", "광고", "업체", "시공", "인테리어업체", "이사", "용달",
        "대출", "보험설계사", "설계사모집", "모집",
    ]
    all_exclude = list(set(default_exclude + exclude_cafes))

    date_from_dt, date_to_dt = None, None
    if date_from:
        try:
            date_from_dt = dt.strptime(date_from, "%Y-%m-%d")
        except Exception:
            pass
    if date_to:
        try:
            date_to_dt = dt.strptime(date_to, "%Y-%m-%d")
        except Exception:
            pass

    logger.info("Crawl started: sid=%s, bk=%s, keywords=%d, target=%d", sid, bk, len(keywords), target)

    for kw in keywords:
        if total >= target:
            break
        query = f"{bk} {kw}"
        logger.info("Searching keyword: %s", query)
        for start in range(1, 1001, 100):
            if total >= target:
                break
            data = search_naver_cafe(query, 100, start)
            if not data or "items" not in data:
                logger.warning("No data for query=%s start=%d, moving to next keyword", query, start)
                break
            for item in data.get("items", []):
                if total >= target:
                    break
                title = clean_text(item.get("title", ""))
                desc = clean_text(item.get("description", ""))
                link = item.get("link", "")
                cafe = item.get("cafename", "")
                postdate = item.get("postdate", "")

                if postdate and (date_from_dt or date_to_dt):
                    try:
                        post_dt = dt.strptime(postdate, "%Y%m%d")
                        if date_from_dt and post_dt < date_from_dt:
                            continue
                        if date_to_dt and post_dt > date_to_dt:
                            continue
                    except Exception:
                        pass

                combined = (title + " " + desc).lower()
                cafe_lower = cafe.lower()
                if any(ad.lower() in combined for ad in ad_filter):
                    continue
                if any(ex.lower() in cafe_lower for ex in all_exclude):
                    continue
                if cafes_filter and not any(c.lower() in cafe_lower for c in cafes_filter):
                    continue
                if bk.lower() not in (title + " " + desc).lower():
                    continue

                results.append({
                    "kw": kw, "title": title, "desc": desc,
                    "link": link, "cafe": cafe, "date": postdate,
                })
                total += 1
                job_manager.update("crawl", sid, total=total)

            if len(results) >= 500:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                try:
                    save_jsonl(f"crawl/{sid}/{ts}.jsonl", results)
                except Exception as e:
                    logger.error("S3 save failed: %s", e)
                results = []
            time.sleep(0.1)

    if results:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        try:
            save_jsonl(f"crawl/{sid}/{ts}.jsonl", results)
        except Exception as e:
            logger.error("S3 final save failed: %s", e)

    logger.info("Crawl finished: sid=%s, total=%d", sid, total)
    return total
