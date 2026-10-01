import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.context import store, versions
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.s3 import save_json, load_json, list_prefixes, delete_object
from app.jobs.manager import job_manager
from app.models.schemas import SessionSaveRequest

router = APIRouter()


def _completion(sid, data, version=None):
    """Project durable local evidence without refreshing runs or writing state."""
    def crawl_done():
        from app.crawl.control import phase_state

        collection = data.get("collectionId")
        return bool(collection and phase_state(sid, collection) == "done")

    def labeling_done():
        from app.work.status import database_path

        if data.get("labeling", {}).get("status") == "done":
            return True
        selected = version or data.get("version")
        if not selected:
            selected = (store.read_json(store.root_dir(sid) / "meta.json") or {}).get("activeVersion")
        path = database_path(sid)
        if not selected or not path.exists():
            return False
        latest = {}
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            for labeler, state in db.execute("""SELECT labeler, state FROM runs
                    WHERE version=? AND kind='judge'
                    ORDER BY started_at DESC, rowid DESC""", (selected,)):
                latest.setdefault(labeler, state)
        return all(latest.get(name) == "done" for name in ("jev", "gpt"))

    def clusters_done():
        # Clustering currently stores session-scoped results, not version artifacts.
        job = job_manager.get("cluster", sid)
        if job.get("status") == "done" and bool(job.get("clusters")):
            return True
        root = Path(settings.local_data_dir)
        return any(
            p.is_file() and p.stat().st_size > 0
            for folder, pattern in (("clusters", "cluster_*.jsonl"), ("clusters_refined", "data_*.jsonl"))
            for p in (root / folder / sid).glob(pattern)
        )

    def export_done():
        export_ref = data.get("training", {}).get("exportRef")
        return isinstance(export_ref, str) and bool(export_ref.strip())

    result = {}
    for field, compute in (
        ("crawlDone", crawl_done),
        ("prepDone", lambda: data.get("prep", {}).get("status") == "done"),
        ("labelingDone", labeling_done),
        ("exportDone", export_done),
        ("clustersDone", clusters_done),
    ):
        try:
            result[field] = compute()
        except Exception:
            # Completion is optional evidence; one broken source must not block
            # session/version reads or discard the other fields' evidence.
            result[field] = False
    return result


@router.post("/save-session")
def save_session(req: SessionSaveRequest, version: str | None = None):
    try:
        with store.locked(req.sid):
            existing = store.load_session(req.sid)
            if (existing and not store.is_legacy(existing)) or req.data.get("schemaVersion") == 2:
                owned = {"projectContext", "knownInsights", "keywords", "keywordRounds", "coverage",
                         "crawlConfig", "collectionId", "drafts", "schemaVersion", "sid",
                         "prep", "labeling", "training", "completion",
                         "parentVersion", "restartFrom", "stale", "updatedAt",
                         "bk", "pd", "problemDef", "allKw", "_pendingKw", "ages", "ar", "gens"}
                patch = {k: v for k, v in req.data.items() if k not in owned and not k.startswith("version")}
                if existing is None:
                    patch.update(schemaVersion=2, sid=req.sid)
                if existing is not None:
                    store.assert_writable(req.sid, version)
                store._update_locked(req.sid, patch)
            else:
                save_json(f"sessions/{req.sid}/session.json", req.data)
        return {"status": "saved"}
    except store.StoreError as exc:
        return JSONResponse(status_code=exc.status, content={"status": "error", "error": {"kind": exc.kind, "message": str(exc)}})
    except Exception:
        return {"status": "error", "error": "저장소 작업에 실패했습니다"}


@router.get("/session/{sid}")
def get_session(sid: str, version: str | None = None):
    try:
        data = versions._data(sid, version) if version else store.load_session(sid) or load_json(f"sessions/{sid}/session.json")
        if data and not store.is_legacy(data):
            data = {**data, "completion": _completion(sid, data, version)}
    except store.StoreError as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=exc.status, content={"status": "error", "error": {"kind": exc.kind, "message": str(exc)}})
    if data:
        return {"status": "ok", "data": data}
    return {"status": "not_found", "data": None}


@router.get("/sessions")
def list_sessions():
    try:
        prefixes = set(list_prefixes("sessions/"))
        root = Path(settings.local_data_dir) / "sessions"
        if root.exists():
            prefixes.update(f"sessions/{p.name}/" for p in root.iterdir() if p.is_dir())
        sessions = []
        recency = {}
        for p in prefixes:
            sid = p.replace("sessions/", "").rstrip("/")
            try:
                d = store.load_session(sid) or load_json(f"sessions/{sid}/session.json")
                if not d:
                    continue
                updated_at = d.get("updatedAt") or d.get("createdAt")
                try:
                    timestamp = datetime.fromisoformat(updated_at)
                    if timestamp.tzinfo is None:
                        timestamp = timestamp.replace(tzinfo=timezone.utc)
                    recency[sid] = timestamp.timestamp()
                except (TypeError, ValueError):
                    path = store.session_dir(sid) / "session.json"
                    recency[sid] = path.stat().st_mtime if path.exists() else 0.0
                    updated_at = datetime.fromtimestamp(recency[sid], timezone.utc).isoformat()
                sessions.append({"sid": sid, "bk": d.get("projectContext", {}).get("bk", d.get("bk", "")),
                                 "step": d.get("step", ""), "schemaVersion": d.get("schemaVersion"),
                                 "legacy": store.is_legacy(d), "activity": store.session_activity(sid, d),
                                 "updatedAt": updated_at})
            except Exception:
                recency[sid] = 0.0
                sessions.append({"sid": sid, "status": "unreadable"})
        sessions.sort(key=lambda item: (recency[item["sid"]], item["sid"]), reverse=True)
        sessions.sort(key=lambda item: store.activity_rank(item.get("activity")))
        return {"status": "ok", "sessions": sessions[:20]}
    except Exception:
        return {"status": "error", "sessions": []}


@router.delete("/delete-session/{sid}")
def delete_session(sid: str, version: str | None = None):
    try:
        root = store.root_dir(sid)
        if (root / "meta.json").exists():
            with store.locked(sid):
                try:
                    session = store.load_session(sid)
                except (OSError, ValueError):
                    session = None
                if session is not None:
                    store.assert_writable(sid, version)
                # Keep the lock inode stable for writers already waiting on it.
                for child in root.iterdir():
                    if child.name == ".lock":
                        continue
                    if child.is_symlink() or child.is_file():
                        child.unlink()
                    elif child.is_dir():
                        shutil.rmtree(child)
        else:
            delete_object(f"sessions/{sid}/session.json")
        return {"status": "ok"}
    except store.StoreError as exc:
        return JSONResponse(status_code=exc.status, content={"status": "error", "error": {"kind": exc.kind, "message": str(exc)}})
    except Exception:
        return {"status": "error", "error": "저장소 작업에 실패했습니다"}


@router.get("/pipeline-status/{sid}")
def pipeline_status(sid: str):
    result = {
        "session": None,
        "crawl": job_manager.get("crawl", sid),
        "preprocess": job_manager.get("preprocess", sid),
        "train": job_manager.get("train", sid),
        "cluster": job_manager.get("cluster", sid),
        "embed": job_manager.get("embed", sid),
        "persona": job_manager.get("persona", sid),
    }
    data = store.load_session(sid) or load_json(f"sessions/{sid}/session.json")
    if data:
        result["session"] = data
    return result
