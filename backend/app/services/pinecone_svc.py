from app.config import settings
from app.services.voyage import get_embeddings


def search_similar(sid: str, query: str, top_k: int = 10) -> list[dict]:
    """Mini-RAG: Voyage embedding + Pinecone search."""
    try:
        from pinecone import Pinecone

        pc = Pinecone(api_key=settings.pinecone_api_key)
    except Exception:
        return []
    try:
        index_name = f"cx-{sid.replace('_', '-').lower()}"[:45]
        existing = [idx.name for idx in pc.list_indexes()]
        if index_name not in existing:
            return []
        index = pc.Index(index_name)
        query_emb = get_embeddings([query])[0]
        results = index.query(vector=query_emb, top_k=top_k, include_metadata=True)
        return [{"score": m.score, **m.metadata} for m in results.matches]
    except Exception as e:
        print(f"Search error: {e}")
        return []
