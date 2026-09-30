import json
import re
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.context.store import load_session
from app.context.labels import LABELS
from app.crawl.writer import read_docs

from app.services.s3 import load_data, save_jsonl
from app.jobs.manager import job_manager


def _crawl_docs(sid: str) -> list[dict]:
    """Snapshot the active pointer, then read child first so its doc_id wins."""
    session = load_session(sid) or {}
    cid = session.get("collectionId")
    if not cid:
        return load_data(f"crawl/{sid}/")

    base = Path(settings.local_data_dir) / "crawl" / sid / "collections"
    collections = set()
    docs = {}
    while cid:
        if not isinstance(cid, str) or not re.fullmatch(r"c[1-9][0-9]*", cid):
            raise ValueError("Invalid crawl collection id")
        if cid in collections:
            raise ValueError("Cyclic crawl collection chain")
        collections.add(cid)
        root = base / cid
        try:
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ValueError(f"수집본을 읽을 수 없습니다 ({cid})") from None
        for doc in read_docs(root / "docs"):
            docs.setdefault(doc["doc_id"], doc)
        cid = manifest.get("parent")
    return list(docs.values())


def _compat_fields(item: dict) -> dict:
    if "doc_id" not in item:
        return dict(item)
    source = item.get("source", "")
    comments = "\n".join(comment.get("text", "") for comment in item.get("comments", []))
    return {
        **item,
        "desc": (item.get("body", "") + "\n" + comments)[:4000],
        "cafe": item.get("src_meta", {}).get("cafe") or LABELS["channels"].get(source, source),
        "link": item.get("url", ""),
    }



def _passes_quality(item: dict) -> bool:
    if "doc_id" not in item:
        # Preserve the legacy acceptance rule for old crawl files.
        return len(item.get("title", "")) >= 5 or len(item.get("desc", "")) >= 10
    if item.get("fetch_level") == "snippet":
        description = item.get("snippet", "") or item.get("body", "")
        return len(item.get("title", "")) >= 5 or len(description) >= 10
    # Full documents (including title-less YouTube threads) use body alone.
    return len(item.get("body", "")) >= 10


def preprocess_data(config: dict) -> None:
    sid = config.get("sid", "s0")
    ad_filter = config.get("adFilter", [])
    exclude_cafes = config.get("excludeCafes", [])

    if isinstance(exclude_cafes, str):
        exclude_cafes = [x.strip() for x in exclude_cafes.split(",") if x.strip()]

    try:
        all_data = _crawl_docs(sid)
        seen: set[str] = set()
        original = len(all_data)
        filtered = []
        for idx, raw in enumerate(all_data):
            item = _compat_fields(raw)
            title = item.get("title", "")
            desc = item.get("desc", "")
            link = item.get("link", "")
            if any(ad.lower() in (title + " " + desc).lower() for ad in ad_filter):
                continue
            cafe = item.get("cafe", "").lower()
            cafe_id = str((item.get("src_meta") or {}).get("cafe_id") or "").lower()
            if exclude_cafes and any(ex.lower() in cafe or ex.lower() in cafe_id for ex in exclude_cafes):
                continue
            identity = item.get("doc_id", link)
            if identity in seen:
                continue
            seen.add(identity)
            item["idx"] = idx
            if not _passes_quality(item):
                continue
            filtered.append(item)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_jsonl(f"preprocessed/{sid}/{ts}.jsonl", filtered)
        job_manager.set("preprocess", sid, {
            "status": "done", "original": original, "filtered": len(filtered),
        })
    except Exception as e:
        job_manager.set("preprocess", sid, {"status": "error", "error": str(e)})
