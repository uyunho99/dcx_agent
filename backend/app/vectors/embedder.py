"""Interchangeable production and deterministic offline embedders."""
import hashlib
from typing import Literal, Protocol

import numpy as np

from app.config import settings
from app.services.voyage import get_embeddings


class Embedder(Protocol):
    name: str
    model: str
    dim: int

    def embed(self, texts: list[str], input_type: Literal['document', 'query'] = 'document') -> np.ndarray:
        """Return float32 [n, dim], with zero rows for failed embeddings."""
        ...


class EmbedderUnconnected(RuntimeError):
    """Voyage credentials have not been configured."""


def embedder_name(meta: dict) -> str:
    """Display the actual backend/model without changing cache identity."""
    return 'fake' if meta.get('name') == 'fake' else meta.get('model', meta.get('name', ''))


class VoyageEmbedder:
    name = 'voyage'

    def __init__(self):
        if settings.voyage_api_key.strip() in {'', 'x'}:
            raise EmbedderUnconnected('Voyage API key is not configured')
        self.model = settings.embed_model
        self.dim = settings.embed_dim

    def embed(self, texts: list[str], input_type: Literal['document', 'query'] = 'document') -> np.ndarray:
        return np.asarray(get_embeddings(texts, input_type=input_type), dtype=np.float32).reshape(len(texts), self.dim)


class FakeEmbedder:
    name = 'fake'

    def __init__(self):
        self.model = settings.embed_model
        self.dim = settings.embed_dim

    def embed(self, texts: list[str], input_type: Literal['document', 'query'] = 'document') -> np.ndarray:
        result = np.empty((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            seed = int.from_bytes(hashlib.sha256(text.encode('utf-8')).digest(), 'big')
            vector = np.random.default_rng(seed).standard_normal(self.dim).astype(np.float32)
            result[row] = vector / np.linalg.norm(vector)
        return result


def get_embedder() -> Embedder:
    return FakeEmbedder() if settings.embed_backend == 'fake' else VoyageEmbedder()
