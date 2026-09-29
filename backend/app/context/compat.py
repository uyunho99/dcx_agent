"""Compatibility defaults for later-stage requests."""
import logging

from app.context.store import load_session

logger = logging.getLogger(__name__)


def fill_bk_problem(config: dict, sid: str) -> None:
    """Fill empty legacy fields; unavailable sessions leave the request intact."""
    if config.get("bk") and config.get("problemDef"):
        return
    try:
        session = load_session(sid)
        if session is None:
            logger.warning("Context fallback unavailable: sid=%s", sid)
            return
        context = session.get("projectContext") or {}
        question = context.get("researchQuestion") or {}
        # Resolve both before mutating so corrupt context cannot partially fill.
        bk = context.get("bk") or ""
        problem = question.get("text") or ""
    except Exception:
        logger.warning("Context fallback unavailable: sid=%s", sid)
        return
    if not config.get("bk"):
        config["bk"] = bk
    if not config.get("problemDef"):
        config["problemDef"] = problem
