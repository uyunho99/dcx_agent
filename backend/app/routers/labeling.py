import random
from fastapi import APIRouter, Query

from app.services.s3 import load_data

router = APIRouter()


@router.get("/sample/{sid}")
def get_sample(sid: str, percent: int = Query(2)):
    try:
        all_data = load_data(f"preprocessed/{sid}/")
        total = len(all_data)
        cnt = max(10, int(total * percent / 100))
        samples = random.sample(all_data, min(cnt, len(all_data))) if all_data else []
        return {"status": "ok", "samples": samples[:20], "total": total}
    except Exception:
        return {"status": "error", "samples": [], "total": 0}
