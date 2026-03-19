import threading
from fastapi import APIRouter

from app.services.preprocessing import preprocess_data
from app.jobs.manager import job_manager
from app.models.schemas import PreprocessRequest

router = APIRouter()


@router.post("/preprocess")
def start_preprocess(req: PreprocessRequest):
    sid = req.sid
    config = req.model_dump()
    job_manager.set("preprocess", sid, {"status": "running"})
    threading.Thread(target=lambda: preprocess_data(config), daemon=True).start()
    return {"sid": sid, "status": "started"}


@router.get("/preprocess-status/{sid}")
def get_preprocess_status(sid: str):
    return job_manager.get("preprocess", sid)
