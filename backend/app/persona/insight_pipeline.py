"""Session-serialized insight work; published revisions are durable checkpoints.

The dedicated lock spans inference, but is distinct from sessions.locked so
PersonaStore mutations can safely acquire their own short-lived session lock.
"""
from contextlib import contextmanager
import fcntl

from app.context import store as sessions
from app.context.versions import version_dir
from app.llm import registry
from app.persona.insights import derive
from app.persona.concepts import make_concept
from app.persona.store import PersonaStore
from app.vectors.embedder import get_embedder
from app.segment.pipeline import LLM_REASON


@contextmanager
def serialized(sid):
    root = sessions.root_dir(sid)
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.insight.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def publish_status(sid, version, status, **values):
    with sessions.locked(sid):
        sessions.assert_writable(sid, version)
        path = version_dir(sid, version) / 'session.json'
        data = sessions.read_json(path)
        state = data.setdefault('insight', {})
        state.setdefault('confirmed', [])
        state.setdefault('revision', 0)
        state.update(status=status, **values)
        if status == 'done':
            current = PersonaStore.open(sid, version).read('insights') or {}
            state.update(revision=current.get('revision', 0), savedAt=sessions.now())
            available = {row['id'] for row in current.get('items', [])}
            state['confirmed'] = [i for i in state['confirmed'] if i in available]
            if state['revision'] and 'stage8' not in data.get('stale', {}):
                data.setdefault('completion', {})['insightDone'] = True
        sessions.write_json(path, data)


class _Stopped(BaseException):
    pass


class _Unavailable(BaseException):
    pass


def run(context):
    sid, version = context.sid, context.version
    with serialized(sid):
        data = sessions.assert_writable(sid, version)
        store = PersonaStore.open(sid, version)
        if data.get('persona', {}).get('status') != 'done' or 'stage8' in data.get('stale', {}):
            raise sessions.StoreError('Persona required', 409, 'persona_required')
        mode = context.args.get('mode', 'derive')
        if mode not in ('derive', 'concept'):
            raise sessions.StoreError('Invalid insight mode', 400, 'validation')
        current = store.read('insights') or {}
        ids = [row['id'] for row in current.get('items', [])]
        target = context.args.get('target')
        targets = ids if target is None else [target] if isinstance(target, str) else target
        if mode == 'concept' and (not isinstance(targets, list) or not targets or
                any(not isinstance(i, str) or i not in ids for i in targets)):
            raise sessions.StoreError('Unknown insight target', 400, 'validation')
        publish_status(sid, version, 'running', run=context.run_id, reason=None)

        def pulse():
            if context.should_stop():
                raise _Stopped()
            context.heartbeat(0, {'mode': mode})
            if context.should_stop():
                raise _Stopped()
            sessions.assert_writable(sid, version)

        def call(task):
            pulse()
            try:
                result = registry.run_task(task)
            except (TimeoutError, ConnectionError) as exc:
                raise _Unavailable() from exc
            pulse()
            if not result.ok and result.error and result.error.kind in ('backend', 'timeout', 'interrupted'):
                raise _Unavailable()
            return result

        try:
            pulse()
            if mode == 'derive':
                if not current.get('revision'):
                    derive(sid, version, run_task=call, embedder=get_embedder())
            else:
                for insight_id in dict.fromkeys(targets):
                    pulse()
                    done = {row.get('insight_id', row.get('id'))
                            for row in (store.read('concepts') or {}).get('items', [])}
                    if insight_id not in done:
                        make_concept(sid, version, insight_id, run_task=call)
            pulse()
            publish_status(sid, version, 'done')
            context.heartbeat(1, {'mode': mode})
        except _Stopped:
            publish_status(sid, version, 'interrupted')
        except _Unavailable:
            publish_status(sid, version, 'interrupted', reason=LLM_REASON)
            raise
        except Exception:
            publish_status(sid, version, 'failed')
            raise
