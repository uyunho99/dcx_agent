"""Optional hands-off chaining: finished crawl -> preprocessing -> labeling.

Enabled per session (`autoChain: true`). Each hook reuses the same entry points as
the screen buttons, so every existing guard still applies; failures are recorded
in `autoChainStatus` and never raise into the finishing worker.
"""
import logging

from app.context import store

logger = logging.getLogger(__name__)


def enabled(sid):
    session = store.load_session(sid)
    return bool(session and session.get('autoChain'))


def _note(sid, **values):
    try:
        store.update_session(sid, {'autoChainStatus': {**values, 'at': store.now()}})
    except Exception as exc:  # Status is advisory only.
        logger.warning('autochain status write failed (%s)', type(exc).__name__)


def after_crawl(sid):
    if not enabled(sid):
        return
    from app.routers.prep import run as start_prep
    try:
        result = start_prep(sid)
    except Exception as exc:
        _note(sid, stage='prep', state='failed', error=str(exc)[:300])
        return
    _note(sid, stage='prep', state=result.get('status'))
    if result.get('status') == 'done':  # Reused an existing preparation: no worker will finish.
        after_prep(sid)


def after_prep(sid, version=None):
    if not enabled(sid):
        return
    from app.routers.labeling_v2 import start as start_labeling
    try:
        start_labeling(sid, version)
    except Exception as exc:
        _note(sid, stage='labeling', state='failed', error=str(exc)[:300])
        return
    _note(sid, stage='labeling', state='running')
