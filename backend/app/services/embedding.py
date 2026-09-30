from app.jobs.manager import job_manager


def run_embedding(config: dict) -> None:
    """Stage 6.5 needs no upload; retrieval uses stage-three vectors."""
    sid = config.get("sid", "s0")
    job_manager.set("embed", sid, {
        "status": "done", "progress": 100, "phase": "3단계 벡터 사용",
        "message": "3단계 벡터 사용",
    })
