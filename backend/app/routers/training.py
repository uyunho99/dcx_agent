import threading
from fastapi import APIRouter
from app.context.store import load_session

from app.services.training import train_models
from app.jobs.manager import job_manager
from app.models.schemas import TrainRequest

router = APIRouter()


@router.post("/train")
def start_train(req: TrainRequest):
    sid = req.sid
    config = req.model_dump()
    if not config.get("bk") or not config.get("problemDef"):
        context = (load_session(sid) or {}).get("projectContext", {})
        if not config.get("bk"):
            config["bk"] = context.get("bk", "")
        if not config.get("problemDef"):
            config["problemDef"] = context.get("researchQuestion", {}).get("text", "")
    job_manager.set("train", sid, {"status": "running", "phase": "init", "progress": 0})
    threading.Thread(target=lambda: train_models(config), daemon=True).start()
    return {"sid": sid, "status": "started"}


@router.get("/train-status/{sid}")
def get_train_status(sid: str):
    return job_manager.get("train", sid)
