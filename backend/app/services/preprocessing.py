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


def _crawl_docs(sid: str, session: dict | None = None) -> list[dict]:
    """Snapshot the active pointer, then read child first so its doc_id wins."""
    session = (load_session(sid) or {}) if session is None else session
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



def _passes_quality(item: dict, min_body_chars: int = 10) -> bool:
    if "doc_id" not in item:
        # Preserve the legacy acceptance rule for old crawl files.
        return len(item.get("title", "")) >= 5 or len(item.get("desc", "")) >= 10
    if item.get("fetch_level") == "snippet":
        description = item.get("snippet", "") or item.get("body", "")
        return len(item.get("title", "")) >= 5 or len(description) >= 10
    # Full documents (including title-less YouTube threads) use body alone.
    return len(item.get("body", "")) >= min_body_chars


def filter_documents(documents, ad_filter=(), excluded=(), min_body_chars=10, *, full_text=False):
    """Shared D-084–086 rules; new prep uses uncapped body/comments for ads."""
    seen = set()
    filtered = []
    removed = dict(ad=0, excluded_source=0, duplicate=0, too_short=0)
    for idx, raw in enumerate(documents):
        item = _compat_fields(raw)
        text = item.get('title', '') + ' ' + item.get('desc', '')
        if full_text:
            text = item.get('body', '') + '\n' + '\n'.join(
                c.get('text', '') for c in item.get('comments', []))
        cafe = item.get('cafe', '').lower()
        cafe_id = str((item.get('src_meta') or {}).get('cafe_id') or '').lower()
        identity = item.get('doc_id', item.get('link', ''))
        reason = None
        if any(ad.lower() in text.lower() for ad in ad_filter):
            reason = 'ad'
        elif any(ex.lower() in cafe or ex.lower() in cafe_id or
                 (full_text and ex.lower() == item.get('source', '').lower()) for ex in excluded):
            reason = 'excluded_source'
        elif identity in seen:
            reason = 'duplicate'
        else:
            seen.add(identity)
            if not _passes_quality(item, min_body_chars):
                reason = 'too_short'
        if reason:
            removed[reason] += 1
            continue
        item['idx'] = idx
        filtered.append(item)
    return filtered, removed


class _InlineContext:
    def __init__(self, config):
        self.args = {'config': config}

    def heartbeat(self, progress, detail):
        pass

    def should_pause(self):
        return False

    def should_stop(self):
        return False


def preprocess_data(config: dict) -> None:
    sid = config.get("sid", "s0")
    ad_filter = config.get("adFilter", [])
    exclude_cafes = config.get("excludeCafes", [])

    if isinstance(exclude_cafes, str):
        exclude_cafes = [x.strip() for x in exclude_cafes.split(",") if x.strip()]

    try:
        session = load_session(sid) or {}
        if session.get('schemaVersion') == 2:
            from app.prep.pipeline import run_prep
            from app.vectors.embedder import EmbedderUnconnected
            prep_config = {**session.get('prep', {}).get('config', {}),
                           **{k: v for k, v in config.items() if k not in {'sid', 'version'}}}
            if exclude_cafes:
                prep_config['excludeSources'] = prep_config.get('excludeSources', []) + exclude_cafes
            try:
                root = run_prep(_InlineContext(prep_config), sid, session.get('version', 'v1'))
            except EmbedderUnconnected as error:
                counts = error.prep_counts
                job_manager.set('preprocess', sid, {
                    'status': 'done', 'original': counts['original'], 'filtered': counts['after'],
                    'embedding': 'unconnected',
                })
                return
            report = json.loads((root / 'stage_3.json').read_text(encoding='utf-8'))
            job_manager.set('preprocess', sid, {
                'status': 'done', 'original': report['original'], 'filtered': report['after'],
            })
            return
        all_data = _crawl_docs(sid)
        original = len(all_data)
        filtered, _ = filter_documents(all_data, ad_filter, exclude_cafes)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_jsonl(f"preprocessed/{sid}/{ts}.jsonl", filtered)
        job_manager.set("preprocess", sid, {
            "status": "done", "original": original, "filtered": len(filtered),
        })
    except Exception as e:
        job_manager.set("preprocess", sid, {"status": "error", "error": str(e)})
