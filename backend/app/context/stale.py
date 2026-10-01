"""Remove version-local stale markers at successful stage completion."""
from contextlib import nullcontext
import os
import time

from app.context import store, versions
from app.work.status import transaction


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


def judge_done(ctx):
    """Publish successful exhaustion and clear stage4 once both labelers finish.

    The generic worker normally publishes done after run_worker returns. Doing
    it here lets the last judge observe both completions without a polling race.
    Its final UPDATE only touches active runs, so this terminal state survives.
    Older failed attempts do not block a successfully completed retry.
    """
    with store.locked(ctx.sid):
        with transaction(ctx.sid) as db:
            changed = db.execute("""UPDATE runs SET state='done', heartbeat_at=?
                WHERE run_id=? AND version=? AND kind='judge' AND pid=?
                AND state='running' AND action IS NOT 'stop' AND action IS NOT 'pause'""",
                (time.time(), ctx.run_id, ctx.version, os.getpid())).rowcount
            if not changed:
                return
            latest = {}
            for row in db.execute("""SELECT labeler, state FROM runs
                    WHERE version=? AND kind='judge'
                    ORDER BY started_at DESC, rowid DESC""", (ctx.version,)):
                latest.setdefault(row['labeler'], row['state'])
            complete = all(latest.get(name) == 'done' for name in ('jev', 'gpt'))
        if complete:
            path = versions.version_dir(ctx.sid, ctx.version) / 'session.json'
            data = store.read_json(path)
            if data is not None:
                data.setdefault('labeling', {})['status'] = 'done'
                data.get('stale', {}).pop('stage4', None)
                store.write_json(path, data)
