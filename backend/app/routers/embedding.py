import threading
from fastapi import APIRouter

from app.services.embedding import run_embedding
from app.jobs.manager import job_manager
from app.models.schemas import EmbedRequest

router = APIRouter()


@router.post("/embed")
def start_embed(req: EmbedRequest):
    sid = req.sid
    config = req.model_dump()
    job_manager.set("embed", sid, {"status": "running", "progress": 0})
    threading.Thread(target=lambda: run_embedding(config), daemon=True).start()
    return {"sid": sid, "status": "started"}


@router.get("/embed-status/{sid}")
def get_embed_status(sid: str):
    return job_manager.get("embed", sid)
