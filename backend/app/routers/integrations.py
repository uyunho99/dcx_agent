"""Public connection metadata; credentials are never returned."""
from fastapi import APIRouter

from app.external.base import integration_status

router = APIRouter()


@router.get("/integrations")
def integrations():
    return integration_status()
