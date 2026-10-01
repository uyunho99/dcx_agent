import hashlib
from importlib.metadata import version
import json
from typing import Literal

from pydantic import BaseModel, Field

from app.config import settings
from app.prep.boilerplate import default_boilerplate
from app.vectors.embedder import Embedder


def analyzer_version() -> str:
    return 'kiwi-' + version('kiwipiepy')


class PrepConfig(BaseModel):
    adFilter: list[str] = Field(default_factory=list)
    excludeSources: list[str] = Field(default_factory=list)
    minBodyChars: int = Field(default=10, ge=0)
    boilerplate: dict[str, list[str]] = Field(default_factory=default_boilerplate)
    analyzer: Literal['kiwi'] = 'kiwi'
    tokenPos: list[str] = Field(default_factory=lambda: ['NNG', 'NNP', 'VV', 'VA', 'XR'])
    embedder: Literal['voyage', 'fake'] = Field(default_factory=lambda: settings.embed_backend)
    embedModel: str = Field(default_factory=lambda: settings.embed_model)
    embedDim: int = Field(default_factory=lambda: settings.embed_dim, gt=0)


def prep_key(collection_id: str, cfg: PrepConfig, embedder: Embedder) -> str:
    config = cfg.model_dump()
    for field in ('adFilter', 'excludeSources', 'tokenPos'):
        config[field] = sorted(set(config[field]))
    config['boilerplate'] = {k: sorted(set(v)) for k, v in config['boilerplate'].items()}
    payload = dict(collectionId=collection_id, config=config,
                   embedder=dict(name=embedder.name, model=embedder.model, dim=embedder.dim),
                   analyzer=analyzer_version())
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return 'p_' + hashlib.sha256(encoded.encode()).hexdigest()[:12]
