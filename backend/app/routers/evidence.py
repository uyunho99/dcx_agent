"""STEP 09 routes; register router in main.py during controller integration."""
from typing import Annotated, Literal
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, ConfigDict, StringConstraints
from app.jobs.manager import job_manager
from app.services import evidence

router = APIRouter(prefix='/api/evidence', tags=['evidence'])
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r'^[A-Za-z0-9_-]+$', min_length=1)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Sort = Literal['quality', 'relevance']


class Filters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    cluster_id: Identifier
    persona_id: Identifier
    context_id: Identifier


class CollectRequest(BaseModel):
    sid: Identifier
    persona_id: Identifier


class SearchRequest(BaseModel):
    sid: Identifier
    query: Text
    filters: Filters
    sort_by: Sort = 'quality'


def _call(fn, *args):
    try:
        return fn(*args)
    except evidence.RetrievalUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post('/collect', status_code=202)
def collect(req: CollectRequest, background_tasks: BackgroundTasks):
    _call(evidence.load_inputs, req.sid, req.persona_id)
    key = evidence.job_key(req.sid, req.persona_id)
    # The shared manager supports fixed job types only. Use a namespaced key in
    # its existing persona bucket, without altering another task's manager file.
    if job_manager.get('persona', key).get('status') == 'running':
        raise HTTPException(409, 'Evidence collection already running')
    job_manager.set('persona', key, dict(status='running', progress=0, phase='queued'))
    background_tasks.add_task(evidence.run_collect, req.sid, req.persona_id)
    return dict(sid=req.sid, persona_id=req.persona_id, status='started', job_id=key)


@router.post('/search')
def search(req: SearchRequest):
    return _call(evidence.search, req.sid, req.query, req.filters.model_dump(), req.sort_by)


@router.get('/status/{sid}/{persona_id}')
def status(sid: Identifier, persona_id: Identifier):
    return job_manager.get('persona', evidence.job_key(sid, persona_id))


@router.get('/{sid}/{persona_id}')
def get_package(sid: Identifier, persona_id: Identifier, sort_by: Sort = 'quality'):
    return _call(evidence.get_package, sid, persona_id, sort_by)
