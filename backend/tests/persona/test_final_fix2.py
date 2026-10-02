"""Round-two regressions, exercising real source and publication paths."""
from concurrent.futures import ThreadPoolExecutor
import pytest

from app.context import store as sessions
from app.context.versions import version_dir
from app.persona import chat, insights, insight_pipeline, pipeline
from app.routers import stage8
from tests.persona.test_insights import env
from tests.persona.test_chat import ready, edit, context
from tests.persona.test_pipeline import setup


def test_n4_only_changed_insight_concept_is_outdated(ready):
    _, store, rows, _ = ready
    store.new_revision('concepts', [dict(id=r['id'], insight_revision=1,
        context_ids=r['context_ids'], outdated=False) for r in rows], by='test', message=None)
    rows[0]['context_ids'] = ['CL0-P0-C1']
    assert edit(ready, {'items': rows})['ok']
    concepts = store.read('concepts')['items']
    assert [r['id'] for r in concepts if r['outdated']] == ['I1']


def test_n5_confirm_keeps_hidden_ids(ready):
    session, _, rows, _ = ready
    rows[0]['id'] = 'I4'
    assert edit(ready, {'items': rows})['ok']
    insights.confirm(session.sid, session.version, ['I4', 'I2'])
    chat.revert(session.sid, session.version, 'insights', 1)
    insights.confirm(session.sid, session.version, ['I2', 'I3'])
    chat.revert(session.sid, session.version, 'insights', 2)
    assert set(sessions.load_session(session.sid)['insight']['confirmed']) == {'I4', 'I2', 'I3'}


@pytest.mark.parametrize('operation', ['edit', 'revert'])
def test_n7_busy_persona_rejects_without_waiting_for_lock(ready, operation):
    session = ready[0]
    sessions.update_session(session.sid, {'persona': {'status': 'running'}})
    with ThreadPoolExecutor(1) as pool:
        with insight_pipeline.serialized(session.sid):
            f = pool.submit(chat.edit, session.sid, session.version, 'insights', 'edit') if operation == 'edit' else pool.submit(chat.revert, session.sid, session.version, 'insights', 1)
            with pytest.raises(sessions.StoreError) as exc:
                f.result(timeout=.3)
            assert exc.value.kind == 'persona_required'


@pytest.mark.parametrize('failure', ['source', 'unknown', 'connection'])
def test_n3_n10_real_exception_publishes_korean_reason(ready, monkeypatch, failure):
    from app.llm import registry
    from app.segment.pipeline import LLM_REASON
    session, store, _, _ = ready
    (store.path / 'insights.json').unlink()
    if failure == 'source':
        sessions.update_session(session.sid, {'stale': {'stage8': 'changed while queued'}})
    else:
        def broken(*a, **kw):
            raise (ConnectionError('provider gone') if failure == 'connection' else RuntimeError('private provider detail'))
        monkeypatch.setattr(registry, 'run_task', broken)
    ctx = context(ready, mode='derive')
    with pytest.raises(BaseException) as exc:
        insight_pipeline.run(ctx)
    data = sessions.load_session(session.sid)
    assert data['insight']['status'] == ('interrupted' if failure == 'connection' else 'failed')
    reason = data['insight']['reason']
    assert any('\uac00' <= c <= '\ud7a3' for c in reason)
    if failure == 'connection':
        assert reason == LLM_REASON
    monkeypatch.setattr(stage8.runner, 'status', lambda sid: [dict(kind='insight', version=session.version,
        runId=ctx.run_id, state=data['insight']['status'], error=type(exc.value).__name__)])
    assert stage8.get_insights(session.sid)['worker']['reason'] == reason


@pytest.mark.parametrize('after_chat', [False, True])
def test_n9_old_terminal_worker_does_not_override_reset_or_chat(ready, monkeypatch, after_chat):
    session = ready[0]
    path = version_dir(session.sid, session.version) / 'session.json'
    data = sessions.read_json(path)
    data['insight'] = {'status': 'failed', 'run': 'old', 'reason': insights.FAILURE_COPY}
    sessions.write_json(path, data)
    if after_chat:
        assert edit(ready, {'items': ready[2]})['ok']
    else:
        from app.llm import registry
        monkeypatch.setattr(registry, 'run_task', ready[3].run)
        pipeline.run(context(ready, fresh=True))
    monkeypatch.setattr(stage8.runner, 'status', lambda sid: [dict(kind='insight', version=session.version,
        runId='old', state='failed', error='InsightError')])
    result = stage8.get_insights(session.sid)['worker']
    assert result['status'] == ('done' if after_chat else 'idle')
    assert result['reason'] is None


def test_c1_status_identifies_package_older_than_confirmations(setup, monkeypatch):
    from app.segment.store import SegmentStore
    import sqlite3
    ctx, _, _ = setup
    pipeline.run(ctx)
    with sqlite3.connect(SegmentStore.open(ctx.sid, ctx.version).path) as db:
        db.execute("UPDATE personas SET name='changed' WHERE persona_id='CL0-P0'")
    monkeypatch.setattr(stage8.runner, 'status', lambda sid: [])
    status = stage8.persona_status(ctx.sid)
    assert status['package'] is True
    assert status['evidence_required'] is True


def test_n8_missing_package_completion_is_false_and_unchanged_poll_is_cached(setup, monkeypatch):
    from app.routers.sessions import _completion
    ctx, root, _ = setup
    pipeline.run(ctx)
    data = sessions.load_session(ctx.sid)
    original = pipeline._confirmed_matches
    calls = []
    def counted(*a):
        calls.append(1)
        return original(*a)
    monkeypatch.setattr(pipeline, '_confirmed_matches', counted)
    assert _completion(ctx.sid, data, ctx.version)['personaDone']
    assert _completion(ctx.sid, data, ctx.version)['personaDone']
    assert len(calls) == 1
    import sqlite3
    from app.segment.store import SegmentStore
    with sqlite3.connect(SegmentStore.open(ctx.sid, ctx.version).path) as db:
        db.execute("UPDATE personas SET name='changed' WHERE persona_id='CL0-P0'")
    assert not _completion(ctx.sid, data, ctx.version)['personaDone']
    assert len(calls) == 2
    (root / 'evidence/package.json').unlink()
    assert not _completion(ctx.sid, data, ctx.version)['personaDone']


def test_n9_terminal_worker_from_other_run_is_ignored(ready, monkeypatch):
    session = ready[0]
    sessions.update_session(session.sid, {'insight': {'run': 'new', 'status': 'done'}})
    monkeypatch.setattr(stage8.runner, 'status', lambda sid: [dict(kind='insight', version=session.version,
        runId='old', state='failed', error='InsightError')])
    assert stage8.get_insights(session.sid)['worker']['status'] == 'done'
