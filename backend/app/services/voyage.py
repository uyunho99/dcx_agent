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
            result = vo.embed(batch, model="voyage-multilingual-2")
            all_embs.extend(result.embeddings)
        except Exception as e:
            print(f"Voyage embed error: {e}")
            all_embs.extend([[0.0] * 1024 for _ in batch])
    return all_embs
