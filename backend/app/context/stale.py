"""Remove version-local stale markers at successful stage completion."""
from contextlib import closing, nullcontext
import os
import sqlite3
import time

from app.context import store, versions
from app.work.status import database_path, transaction


def clear_stale(sid, version, stage, *, already_locked=False):
    """Delete one marker, preserving all other session data.

    Publishers holding the session flock must opt out of reacquiring it: flock
    on another file descriptor is not reentrant.
    """
    with nullcontext() if already_locked else store.locked(sid):
        path = versions.version_dir(sid, version) / 'session.json'
        data = store.read_json(path)
        if data is None or stage not in data.get('stale', {}):
            return
        del data['stale'][stage]
        store.write_json(path, data)


def _judges_complete(db, version):
    latest = {}
    for labeler, state in db.execute("""SELECT labeler, state FROM runs
            WHERE version=? AND kind='judge'
            ORDER BY started_at DESC, rowid DESC""", (version,)):
        latest.setdefault(labeler, state)
    return all(latest.get(name) == 'done' for name in ('jev', 'gpt'))


def _publication_pending(data):
    return ('stage4' in data.get('stale', {})
            or data.get('labeling', {}).get('status') != 'done')


def _publish_judges(sid, version):
    """Called under the session lock; reread to preserve concurrent changes."""
    path = versions.version_dir(sid, version) / 'session.json'
    data = store.read_json(path)
    if data is not None and _publication_pending(data):
        data.setdefault('labeling', {})['status'] = 'done'
        data.get('stale', {}).pop('stage4', None)
        store.write_json(path, data)
    return data


def reconcile_judge_done(sid, data, version=None):
    """Repair interrupted publication from durable runs, without refreshing them.

    Normal reads avoid locking when already published or no run database exists.
    A failed recovery must not prevent reading the last saved session.
    """
    try:
        path = database_path(sid)
        if not _publication_pending(data) or not path.exists():
            return data
        with store.locked(sid):
            selected = version or data.get('version')
            if not selected:
                selected = (store.read_json(store.root_dir(sid) / 'meta.json') or {}).get('activeVersion')
            if not selected:
                return data
            with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
                complete = _judges_complete(db, selected)
            if complete:
                return _publish_judges(sid, selected) or data
    except Exception:
        # Durable done rows remain available for the next read/replay to retry.
        pass
    return data


def judge_done(ctx):
    """Publish exhaustion, including replay after a session publication failure.

    Run completion commits first, so a crash or failed JSON write can be repaired
    from durable terminal rows. Older failed attempts do not block a done retry.
    """
    with store.locked(ctx.sid):
        with transaction(ctx.sid) as db:
            changed = db.execute("""UPDATE runs SET state='done', heartbeat_at=?
                WHERE run_id=? AND version=? AND kind='judge' AND pid=?
                AND state='running' AND action IS NOT 'stop' AND action IS NOT 'pause'""",
                (time.time(), ctx.run_id, ctx.version, os.getpid())).rowcount
            if not changed and not db.execute("""SELECT 1 FROM runs
                    WHERE run_id=? AND version=? AND kind='judge' AND state='done'""",
                    (ctx.run_id, ctx.version)).fetchone():
                return
            complete = _judges_complete(db, ctx.version)
        if complete:
            _publish_judges(ctx.sid, ctx.version)
