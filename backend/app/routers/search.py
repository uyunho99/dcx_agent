from fastapi import APIRouter

from app.known.filter import search_docs
from app.models.schemas import SearchRequest

router = APIRouter()


@router.post("/search")
def search(req: SearchRequest):
    result = search_docs(req.sid, [req.query], req.top_k, novel=req.novel)
    return {"status": "ok", "results": result.items[0], "reason": result.reason}
