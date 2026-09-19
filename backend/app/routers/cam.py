"""CAM routes; controller registers this router in main.py."""
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.services import cam

router = APIRouter(prefix='/api/cam', tags=['cam'])


class CamRequest(BaseModel):
    sid: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]*$')
    persona_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]*$')


@router.post('/describe')
def describe(req: CamRequest, background_tasks: BackgroundTasks):
    if cam.get_cam_job(req.sid, req.persona_id).get('status') == 'running':
        raise HTTPException(409, 'CAM generation already running')
    cam.set_cam_job(req.sid, req.persona_id, status='running', progress=0, phase='queued')
    background_tasks.add_task(cam.run_cam, req.model_dump())
    return {'sid': req.sid, 'persona_id': req.persona_id, 'status': 'started'}


@router.get('/status/{sid}/{persona_id}')
def status(sid: str, persona_id: str):
    return cam.get_cam_job(sid, persona_id)


@router.get('/{sid}/{persona_id}')
def get_cam(sid: str, persona_id: str):
    try:
        return cam.load_latest('cam', sid, persona_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
