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
    job_manager.set("crawl", sid, {"status": "running", "total": 0})

    def _run():
        try:
            total = crawl_keywords(config)
            job_manager.set("crawl", sid, {"status": "done", "total": total})
        except Exception as e:
            logger.exception("Crawl failed for sid=%s", sid)
            job_manager.set("crawl", sid, {"status": "error", "error": str(e)})

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

    if status == "done":
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
    return {"status": status, "total": total, "cafe_stats": cafe_stats, "error": error}
