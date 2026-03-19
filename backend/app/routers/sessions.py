import json
from fastapi import APIRouter

from app.services.s3 import save_json, load_json, list_prefixes, delete_object
from app.jobs.manager import job_manager
from app.models.schemas import SessionSaveRequest

router = APIRouter()


@router.post("/save-session")
def save_session(req: SessionSaveRequest):
    try:
        save_json(f"sessions/{req.sid}/session.json", req.data)
        return {"status": "saved"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/session/{sid}")
def get_session(sid: str):
    data = load_json(f"sessions/{sid}/session.json")
    if data:
        return {"status": "ok", "data": data}
    return {"status": "not_found", "data": None}


@router.get("/sessions")
def list_sessions():
    try:
        prefixes = list_prefixes("sessions/")
        sessions = []
        for p in prefixes:
            sid = p.replace("sessions/", "").rstrip("/")
            d = load_json(f"sessions/{sid}/session.json")
            if d:
                sessions.append({"sid": sid, "bk": d.get("bk", ""), "step": d.get("step", "")})
            else:
                sessions.append({"sid": sid, "bk": "", "step": ""})
        return {
            "status": "ok",
            "sessions": sorted(sessions, key=lambda x: x["sid"], reverse=True)[:20],
        }
    except Exception:
        return {"status": "error", "sessions": []}


@router.delete("/delete-session/{sid}")
def delete_session(sid: str):
    try:
        delete_object(f"sessions/{sid}/session.json")
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


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
    data = load_json(f"sessions/{sid}/session.json")
    if data:
        result["session"] = data
    return result
