"""Controller integration: app.include_router(insight.router), no extra prefix.

These endpoints assemble supplied CAM/evidence synchronously without external
calls. If LLM generation is added later, wrap that work with job_manager.
"""

from fastapi import APIRouter, HTTPException

from app.services import insight

router = APIRouter(prefix="/api", tags=["insight"])


def _call(function, *args):
    try:
        return function(*args)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/insight/synthesize")
def synthesize(req: insight.SynthesizeRequest):
    return _call(insight.synthesize, req)


@router.get("/insight/{sid}/{insight_id}")
def get_insight(sid: str, insight_id: str):
    return _call(insight.get_artifact, "insights", sid, insight_id)


@router.post("/insight/{sid}/{insight_id}/confirm")
def confirm(sid: str, insight_id: str):
    return _call(insight.confirm, sid, insight_id)


@router.post("/concept/generate")
def generate(req: insight.GenerateRequest):
    return _call(insight.generate, req)


@router.get("/concept/{sid}/{concept_id}")
def get_concept(sid: str, concept_id: str):
    return _call(insight.get_artifact, "concepts", sid, concept_id)


@router.post("/concept/{sid}/{concept_id}/interviews")
def add_interview(sid: str, concept_id: str, req: insight.Interview):
    return _call(insight.add_interview, sid, concept_id, req)
