import time
import json
import asyncio
import logging
from datetime import datetime, datetime as dt
from collections import Counter

from app.services.naver import search_naver_cafe
from app.services.s3 import save_jsonl, load_data, list_objects, delete_object
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
    mode = config.get("mode", "api_only")
    cookies = config.get("cookies")

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

    job_manager.update("crawl", sid, phase="api_collecting")
    logger.info("Crawl started: sid=%s, bk=%s, keywords=%d, target=%d, mode=%s", sid, bk, len(keywords), target, mode)

    def _stopped():
        return job_manager.is_stop_requested("crawl", sid)

    for kw in keywords:
        if total >= target or _stopped():
            break
        query = f"{bk} {kw}"
        logger.info("Searching keyword: %s", query)
        for start in range(1, 1001, 100):
            if total >= target or _stopped():
                break
            data = search_naver_cafe(query, 100, start)
            if not data or "items" not in data:
                logger.warning("No data for query=%s start=%d, moving to next keyword", query, start)
                break
            for item in data.get("items", []):
                if total >= target or _stopped():
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

    logger.info("Phase 1 (API) finished: sid=%s, total=%d", sid, total)

    # Skip Phase 2 if stop was requested during Phase 1
    if _stopped():
        logger.info("Crawl stopped by user after Phase 1: sid=%s, total=%d", sid, total)
        return total

    # --- Phase 2: Crawl4AI body + metadata enrichment ---
    if mode == "api_crawl4ai" and total > 0:
        job_manager.update("crawl", sid, phase="body_crawling", body_crawled=0, body_failed=0)
        logger.info("Phase 2 (Crawl4AI) starting: sid=%s, urls=%d", sid, total)

        try:
            from app.services.crawl4ai_svc import crawl_cafe_posts

            # Load all records saved in phase 1
            all_records = load_data(f"crawl/{sid}/")
            link_index: dict[str, dict] = {}
            for rec in all_records:
                link_index[rec.get("link", "")] = rec
            urls = [rec.get("link", "") for rec in all_records if rec.get("link")]

            # Progress callback
            def _on_progress(crawled: int, success: int, failed: int):
                job_manager.update("crawl", sid, body_crawled=success, body_failed=failed)

            # Bridge sync → async (daemon thread has no event loop)
            loop = asyncio.new_event_loop()
            try:
                crawl_results = loop.run_until_complete(
                    crawl_cafe_posts(urls, cookies, on_progress=_on_progress, should_stop=_stopped)
                )
            finally:
                loop.close()

            # Merge results into existing records
            body_crawled = 0
            body_failed = 0
            body_lengths = []
            view_counts = []
            comment_counts = []
            like_counts = []
            board_counter: Counter = Counter()
            authors: set = set()

            for cr in crawl_results:
                cr_url = cr.get("url", "")
                cr_meta = cr.get("meta", {})
                cr_status = cr_meta.get("crawl_status", "failed")
                if cr_url in link_index:
                    rec = link_index[cr_url]
                    rec["body"] = cr.get("body") or ""
                    rec["meta"] = cr_meta
                    if cr_status == "success":
                        body_crawled += 1
                        body_lengths.append(cr_meta.get("body_length", 0))
                        if cr_meta.get("view_count") is not None:
                            view_counts.append(cr_meta["view_count"])
                        if cr_meta.get("comment_count") is not None:
                            comment_counts.append(cr_meta["comment_count"])
                        if cr_meta.get("like_count") is not None:
                            like_counts.append(cr_meta["like_count"])
                        if cr_meta.get("board_name"):
                            board_counter[cr_meta["board_name"]] += 1
                        if cr_meta.get("author"):
                            authors.add(cr_meta["author"])
                    else:
                        body_failed += 1

            # Delete old JSONL files and re-save with merged data
            old_files = list_objects(f"crawl/{sid}/")
            for obj in old_files:
                key = obj.get("Key", "")
                if key:
                    delete_object(key)

            merged = list(link_index.values())
            for i in range(0, len(merged), 500):
                batch = merged[i:i + 500]
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                save_jsonl(f"crawl/{sid}/{ts}.jsonl", batch)
                time.sleep(0.01)  # Avoid identical timestamps

            # Compute aggregate stats
            avg_body = round(sum(body_lengths) / len(body_lengths), 1) if body_lengths else 0
            avg_views = round(sum(view_counts) / len(view_counts), 1) if view_counts else 0
            avg_comments = round(sum(comment_counts) / len(comment_counts), 1) if comment_counts else 0
            avg_likes = round(sum(like_counts) / len(like_counts), 1) if like_counts else 0
            top_boards = [{"board": b, "count": c} for b, c in board_counter.most_common(5)]

            meta_summary = {
                "avg_views": avg_views,
                "avg_comments": avg_comments,
                "avg_likes": avg_likes,
                "top_boards": top_boards,
                "unique_authors": len(authors),
            }

            job_manager.update(
                "crawl", sid,
                body_crawled=body_crawled,
                body_failed=body_failed,
                avg_body_length=avg_body,
                meta_summary=meta_summary,
            )

            logger.info("Phase 2 finished: sid=%s, success=%d, failed=%d, avg_body=%.0f",
                         sid, body_crawled, body_failed, avg_body)

        except Exception as e:
            logger.exception("Phase 2 (Crawl4AI) failed: sid=%s", sid)
            job_manager.update("crawl", sid, phase="done", body_crawled=0, body_failed=total)

    logger.info("Crawl finished: sid=%s, total=%d, mode=%s", sid, total, mode)
    return total
