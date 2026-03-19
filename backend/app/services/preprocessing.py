import json
from datetime import datetime

from app.services.s3 import s3, save_jsonl
from app.config import settings
from app.jobs.manager import job_manager


def preprocess_data(config: dict) -> None:
    sid = config.get("sid", "s0")
    ad_filter = config.get("adFilter", [])
    exclude_cafes = config.get("excludeCafes", [])

    if isinstance(exclude_cafes, str):
        exclude_cafes = [x.strip() for x in exclude_cafes.split(",") if x.strip()]

    try:
        resp = s3.list_objects_v2(Bucket=settings.s3_bucket, Prefix=f"crawl/{sid}/")
        all_data, seen = [], set()
        for f in resp.get("Contents", []):
            body = s3.get_object(Bucket=settings.s3_bucket, Key=f["Key"])["Body"]
            for line in body.read().decode("utf-8").strip().split("\n"):
                if line:
                    try:
                        all_data.append(json.loads(line))
                    except Exception:
                        pass

        original = len(all_data)
        filtered = []
        for idx, item in enumerate(all_data):
            title = item.get("title", "")
            desc = item.get("desc", "")
            link = item.get("link", "")
            if any(ad.lower() in (title + " " + desc).lower() for ad in ad_filter):
                continue
            cafe = item.get("cafe", "").lower()
            if exclude_cafes and any(ex.lower() in cafe for ex in exclude_cafes):
                continue
            if link in seen:
                continue
            seen.add(link)
            item["idx"] = idx
            if len(title) < 5 and len(desc) < 10:
                continue
            filtered.append(item)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_jsonl(f"preprocessed/{sid}/{ts}.jsonl", filtered)
        job_manager.set("preprocess", sid, {
            "status": "done", "original": original, "filtered": len(filtered),
        })
    except Exception as e:
        job_manager.set("preprocess", sid, {"status": "error", "error": str(e)})
