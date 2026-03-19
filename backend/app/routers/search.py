from fastapi import APIRouter

from app.services.pinecone_svc import search_similar
from app.models.schemas import SearchRequest

router = APIRouter()


@router.post("/search")
def search_docs(req: SearchRequest):
    results = search_similar(req.sid, req.query, req.top_k)
    return {"status": "ok", "results": results}
