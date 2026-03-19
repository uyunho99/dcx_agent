import json
import threading
from fastapi import APIRouter

from app.services.personas import run_persona
from app.services.s3 import load_data, list_objects, load_json
from app.jobs.manager import job_manager
from app.models.schemas import PersonaRequest
from app.config import settings

router = APIRouter()


@router.post("/persona")
def start_persona(req: PersonaRequest):
    sid = req.sid
    config = req.model_dump()
    job_manager.set("persona", sid, {"status": "running", "progress": 0})
    threading.Thread(target=lambda: run_persona(config), daemon=True).start()
    return {"sid": sid, "status": "started"}


@router.get("/persona-status/{sid}")
def get_persona_status(sid: str):
    job = job_manager.get("persona", sid)
    if job.get("status") in ("running", "done", "error"):
        return job
    # Fallback: check S3
    try:
        objects = list_objects(f"personas/{sid}/")
        if objects:
            latest = sorted(objects, key=lambda x: x["Key"], reverse=True)[0]
            data = load_json(latest["Key"])
            if data:
                return {"status": "done", "personas": data.get("personas", [])}
    except Exception:
        pass
    return {"status": "not_found"}


@router.get("/sna-data/{sid}")
def get_sna_data(sid: str):
    """SNA 시각화용 데이터 반환."""
    try:
        objects = list_objects(f"personas/{sid}/")
        if not objects:
            return {"status": "error", "error": "no persona data"}

        latest = sorted(objects, key=lambda x: x["Key"], reverse=True)[0]
        persona_data = load_json(latest["Key"])
        if not persona_data:
            return {"status": "error", "error": "no persona data"}

        all_data = load_data(f"clusters_refined/{sid}/data_")
        if not all_data:
            all_data = load_data(f"clusters/{sid}/cluster_")

        nodes = []
        links = []

        bk = persona_data.get("bk", "제품")
        nodes.append({"id": "center", "name": bk, "type": "product", "size": 40})

        for cluster in persona_data.get("personas", []):
            cid = cluster.get("cluster_id", 0)
            cname = cluster.get("cluster_name", f"클러스터{cid}")

            cluster_node_id = f"cluster_{cid}"
            cluster_size = len([d for d in all_data if d.get("cluster") == cid - 1])
            nodes.append({
                "id": cluster_node_id, "name": cname, "type": "cluster",
                "size": min(30, 15 + cluster_size // 100),
            })
            links.append({"source": "center", "target": cluster_node_id, "value": cluster_size})

            for i, persona in enumerate(cluster.get("personas", [])):
                persona_node_id = f"persona_{cid}_{i}"
                nodes.append({
                    "id": persona_node_id, "name": persona.get("name", ""),
                    "type": "persona", "size": 12,
                    "pain_point": persona.get("pain_point", ""),
                    "insight": persona.get("insight", ""),
                })
                links.append({"source": cluster_node_id, "target": persona_node_id, "value": 1})

        return {"status": "ok", "nodes": nodes, "links": links, "bk": bk}
    except Exception as e:
        return {"status": "error", "error": str(e)}
