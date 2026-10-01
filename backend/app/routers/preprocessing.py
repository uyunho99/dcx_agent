import threading
from fastapi import APIRouter

from app.services.preprocessing import preprocess_data
from app.jobs.manager import job_manager
from app.models.schemas import PreprocessRequest

from app.routers.context import ContextRoute
from app.context import store
from app.prep.guards import assert_ready, legacy_config

router = APIRouter(route_class=ContextRoute)


@router.post("/preprocess")
def start_preprocess(req: PreprocessRequest):
    sid = req.sid
    config = req.model_dump()
    with store.locked(sid):
        data = store.load_session(sid) or {}
        if data.get('schemaVersion') == 2:
            store.assert_writable(sid)
            assert_ready(sid, data, legacy_config(data, config))
    job_manager.set("preprocess", sid, {"status": "running"})
    threading.Thread(target=lambda: preprocess_data(config), daemon=True).start()
    return {"sid": sid, "status": "started"}


@router.get("/preprocess-status/{sid}")
def get_preprocess_status(sid: str):
    return job_manager.get("preprocess", sid)
