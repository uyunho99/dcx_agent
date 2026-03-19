import threading
from fastapi import APIRouter

from app.services.clustering import run_clustering, refine_clusters
from app.services.s3 import load_data
from app.jobs.manager import job_manager
from app.models.schemas import ClusterRequest, ClusterRefineRequest

router = APIRouter()


@router.post("/cluster")
def start_cluster(req: ClusterRequest):
    sid = req.sid
    config = req.model_dump()
    job_manager.set("cluster", sid, {"status": "running", "phase": "init", "progress": 0})
    threading.Thread(target=lambda: run_clustering(config), daemon=True).start()
    return {"sid": sid, "status": "started"}


@router.get("/cluster-status/{sid}")
def get_cluster_status(sid: str):
    job = job_manager.get("cluster", sid)
    if job.get("status") in ("running", "done", "error"):
        return job

    # Fallback: check S3
    try:
        cd = load_data(f"clusters_refined/{sid}/data_")
        if not cd:
            cd = load_data(f"clusters/{sid}/cluster_")
        if cd:
            cl: dict[int, list] = {}
            for it in cd:
                c = it.get("cluster", 0)
                if c not in cl:
                    cl[c] = []
                cl[c].append(it)

            clusters = {}
            for c in sorted(cl.keys()):
                items = cl[c]
                word_count: dict[str, int] = {}
                for it in items:
                    kw = it.get("kw", "")
                    if kw:
                        word_count[kw] = word_count.get(kw, 0) + 1
                top_kw = sorted(word_count.items(), key=lambda x: -x[1])[:8]
                samples = [
                    {
                        "title": it.get("title", "")[:80],
                        "desc": it.get("desc", "")[:150],
                        "cafe": it.get("cafe", ""),
                        "kw": it.get("kw", ""),
                    }
                    for it in items[:3]
                ]
                clusters[str(c)] = {
                    "size": len(items),
                    "keywords": [k[0] for k in top_kw],
                    "keyword_counts": {k[0]: k[1] for k in top_kw},
                    "samples": samples,
                }
            return {"status": "done", "num_clusters": len(cl), "clusters": clusters}
    except Exception:
        pass
    return {"status": "not_found"}


@router.post("/cluster-refine")
def cluster_refine(req: ClusterRefineRequest):
    return refine_clusters(req.model_dump())
