from app.services.s3 import load_data
from app.services.voyage import get_embeddings
from app.config import settings
from app.jobs.manager import job_manager


def run_embedding(config: dict) -> None:
    """Mini-RAG: Voyage embeddings -> Pinecone storage."""
    sid = config.get("sid", "s0")
    job_manager.set("embed", sid, {"status": "running", "progress": 0, "phase": "loading"})

    try:
        from pinecone import Pinecone

        pc = Pinecone(api_key=settings.pinecone_api_key)

        data = load_data(f"classified/{sid}/relevant_")
        if not data:
            data = load_data(f"preprocessed/{sid}/")
        if not data:
            job_manager.set("embed", sid, {"status": "error", "error": "no data"})
            return

        job_manager.update("embed", sid, progress=10, phase="embedding")

        index_name = f"cx-{sid.replace('_', '-').lower()}"[:45]
        existing = [idx.name for idx in pc.list_indexes()]
        if index_name not in existing:
            pc.create_index(
                name=index_name, dimension=1024, metric="cosine",
                spec={"serverless": {"cloud": "aws", "region": "us-east-1"}},
            )
        index = pc.Index(index_name)

        job_manager.update("embed", sid, progress=20)

        batch_size = 50
        for i in range(0, len(data), batch_size):
            batch = data[i : i + batch_size]
            texts = [f"{d.get('title', '')} {d.get('desc', '')}" for d in batch]
            embeddings = get_embeddings(texts)

            vectors = []
            for j, (d, emb) in enumerate(zip(batch, embeddings)):
                if any(v != 0.0 for v in emb):
                    vectors.append({
                        "id": f"doc_{i + j}",
                        "values": emb,
                        "metadata": {
                            "title": d.get("title", "")[:200],
                            "desc": d.get("desc", "")[:500],
                            "kw": d.get("kw", ""),
                            "cafe": d.get("cafe", ""),
                            "cluster": d.get("cluster", -1),
                        },
                    })
            if vectors:
                index.upsert(vectors=vectors)
            job_manager.update("embed", sid, progress=20 + int(70 * (i + len(batch)) / len(data)))

        job_manager.set("embed", sid, {"status": "done", "progress": 100, "total": len(data), "index": index_name})
    except Exception as e:
        job_manager.set("embed", sid, {"status": "error", "error": str(e)})
