import logging
import threading
from fastapi import APIRouter

from app.services.crawling import crawl_keywords
from app.services.s3 import load_data
from app.jobs.manager import job_manager
from app.models.schemas import CrawlRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/crawl")
def start_crawl(req: CrawlRequest):
    sid = req.sid
    config = req.model_dump()
    job_manager.set("crawl", sid, {"status": "running", "total": 0, "phase": "api_collecting"})

    def _run():
        try:
            total = crawl_keywords(config)
            if job_manager.is_stop_requested("crawl", sid):
                job_manager.update("crawl", sid, status="stopped", total=total, phase="done")
            else:
                job_manager.update("crawl", sid, status="done", total=total, phase="done")
        except Exception as e:
            logger.exception("Crawl failed for sid=%s", sid)
            job_manager.update("crawl", sid, status="error", error=str(e))

    threading.Thread(target=_run, daemon=True).start()
    return {"sid": sid, "status": "started"}


@router.get("/status/{sid}")
def get_status(sid: str):
    job = job_manager.get("crawl", sid)
    status = job.get("status", "not_found")
    total = job.get("total", 0)
    cafe_stats = []

    if status == "not_found":
        try:
            existing = load_data(f"crawl/{sid}/")
            if existing:
                status = "done"
                total = len(existing)
                job_manager.set("crawl", sid, {"status": "done", "total": total})
        except Exception:
            pass

    if status in ("done", "stopped"):
        try:
            all_data = load_data(f"crawl/{sid}/")
            cafe_count: dict[str, int] = {}
            for d in all_data:
                cafe = d.get("cafe", "기타")
                cafe_count[cafe] = cafe_count.get(cafe, 0) + 1
            cafe_stats = sorted(
                [{"cafe": k, "count": v} for k, v in cafe_count.items()],
                key=lambda x: -x["count"],
            )
        except Exception:
            pass

    error = job.get("error", "")
    return {
        "status": status, "total": total, "cafe_stats": cafe_stats, "error": error,
        "phase": job.get("phase"),
        "body_crawled": job.get("body_crawled"),
        "body_failed": job.get("body_failed"),
        "avg_body_length": job.get("avg_body_length"),
        "meta_summary": job.get("meta_summary"),
    }


@router.post("/stop-crawl/{sid}")
def stop_crawl(sid: str):
    success = job_manager.request_stop("crawl", sid)
    return {"status": "stop_requested" if success else "not_running"}
