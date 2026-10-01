from app.context.store import now


def stage3_report(*, original, after, removed, boilerplate_replaced,
                  tokens_written, embedded, embed_failed_zero_vector,
                  prepKey, embedder, analyzer) -> dict:
    return dict(original=original, after=after, removed=removed,
                boilerplate_replaced=boilerplate_replaced, tokens_written=tokens_written,
                embedded=embedded, embed_failed_zero_vector=embed_failed_zero_vector,
                prepKey=prepKey, embedder=embedder, analyzer=analyzer, at=now())
