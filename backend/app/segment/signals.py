"""Document signals for stage six, bundle one."""
from app.lexicon.knu import polarity
from app.segment.inputs import SegmentInput


def document_signals(source: SegmentInput) -> dict[str, dict]:
    """Copy exported entropy verbatim (including legacy zero); score tokens.

    Only selected IDs are emitted. Export rows and token lists are not mutated.
    An absent export entropy remains None; it is never inferred from tagProbs.
    """
    return {doc_id: dict(pred_entropy=source.docs[doc_id].get('pred_entropy'),
                         sentiment=polarity(source.tokens[doc_id]))
            for doc_id in source.ids}
