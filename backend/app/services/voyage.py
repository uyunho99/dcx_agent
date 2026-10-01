import numpy as np
import voyageai

from app.config import settings


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Voyage AI multilingual embeddings for Korean."""
    if len(texts) == 0:
        return []
    vo = voyageai.Client(api_key=settings.voyage_api_key)
    all_embs = []
    for i in range(0, len(texts), 128):
        batch = texts[i : i + 128]
        batch = [t[:2000] if len(t) > 2000 else t for t in batch]
        batch = [t if t.strip() else "빈 문서" for t in batch]
        try:
            result = vo.embed(batch, model=settings.embed_model, output_dimension=settings.embed_dim)
            rows = [[0.0] * settings.embed_dim for _ in batch]
            for row, embedding in enumerate(result.embeddings[:len(batch)]):
                try:
                    vector = np.asarray(embedding, dtype=np.float32)
                except (TypeError, ValueError, OverflowError):
                    continue
                if vector.shape == (settings.embed_dim,) and np.isfinite(vector).all():
                    rows[row] = vector.tolist()
            all_embs.extend(rows)
        except Exception:
            # Provider errors can contain credentials; never print their payload.
            all_embs.extend([[0.0] * settings.embed_dim for _ in batch])
    return all_embs
