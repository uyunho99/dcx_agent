"""Known Insight API."""
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.known import store
from app.routers.context import ContextRoute

router = APIRouter(prefix='/known', route_class=ContextRoute)


class AddKnown(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['statement', 'doc']
    text: str = ''
    doc_id: str | None = None


class PatchKnown(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str | None = None


def view(item):
    return {**item.model_dump(by_alias=True), 'warning': store.UNCONNECTED
            if item.type == 'statement' and item.vectorRow is None else None}


@router.get('/{sid}')
def list_known(sid: str, version: str | None = None):
    return {'items': [view(item) for item in store.list_known(sid, version)]}


@router.post('/{sid}', status_code=201)
def add_known(sid: str, body: AddKnown, version: str | None = None):
    return view(store.add(sid, {**body.model_dump(), 'from': 'rag' if body.type == 'doc' else 'drawer'}, version))


@router.patch('/{sid}/{item_id}')
def update_known(sid: str, item_id: str, body: PatchKnown, version: str | None = None):
    return view(store.update(sid, item_id, body.model_dump(exclude_none=True), version))


@router.delete('/{sid}/{item_id}')
def delete_known(sid: str, item_id: str, version: str | None = None):
    store.delete(sid, item_id, version)
    return {'status': 'ok'}
