from app.config import settings
from app.services.voyage import get_embeddings


def update_context_mappings(sid: str, mappings: list[dict]) -> None:
    """T4 boundary: update document scopes before evidence retrieval.

    Each mapping contains doc_id, cluster_id, persona_id and context_id.
    Implementations must resolve document IDs to indexed vectors, preserve other
    metadata, and return only when all mappings are visible to scoped searches.
    Missing documents or unsuccessful updates must raise, never silently succeed.
    The legacy index uses positional IDs and cannot fulfill this contract.
    """
    raise NotImplementedError('T4 document-context metadata updates are unavailable')


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
