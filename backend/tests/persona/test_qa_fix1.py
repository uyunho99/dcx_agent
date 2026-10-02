import json
import sqlite3
import pytest
from app.llm.fake import FakeBackend
from app.persona.cards import generate_card
from app.persona.package import Package
from app.persona import insight_pipeline
from app.routers import stage8
from app.context import store as sessions
from tests.fixtures.evidence_package import make_package
from tests.persona.test_insights import env
from tests.persona.test_chat import ready, context


def test_echo_cards_all_personas_and_chunks():
    package = Package.model_validate(make_package(big_persona_contexts=10))
    for block in package.personas:
        result = generate_card('qa', block, run_task=FakeBackend().run)
        assert result.status == 'done', block.persona_evidence.persona_id


def test_echo_concept_i3(ready):
    from app.persona.concepts import make_concept
    session = ready[0]
    assert make_concept(session.sid, session.version, 'I3', run_task=FakeBackend().run)['insight_id'] == 'I3'


def test_concept_failure_copy(ready, monkeypatch):
    def broken(*a, **kw):
        raise ValueError('invalid')
    monkeypatch.setattr(insight_pipeline, 'make_concept', broken)
    with pytest.raises(ValueError):
        insight_pipeline.run(context(ready, mode='concept', target='I3'))
    assert stage8.get_insights(ready[0].sid)['worker']['reason'] == '컨셉을 만들지 못했습니다. 다시 시도하세요.'


def test_launch_failure_before_running_is_visible(ready, monkeypatch):
    session = ready[0]
    work = dict(kind='insight', version=session.version, runId='new-run', state='failed')
    def fail_before_running(*args):
        # Target disappears after API validation and before worker preflight.
        ready[1].new_revision('insights', [], by='test', message=None)
        with pytest.raises(sessions.StoreError):
            insight_pipeline.run(context(ready, mode='concept', target='I3'))
        return work
    monkeypatch.setattr(stage8.runner, 'start', fail_before_running)
    monkeypatch.setattr(stage8.runner, 'status', lambda *a: [work])
    monkeypatch.setattr(stage8.pipeline, 'mark_stale_if_changed', lambda *a: False)
    stage8.start_insight(session.sid, stage8.InsightRun(mode='concept', target='I3'))
    result = stage8.get_insights(session.sid)['worker']
    assert result['status'] == 'failed'
    assert result['mode'] == 'concept'
    assert result['target'] == 'I3'
    assert result['reason'] == '컨셉을 만들지 못했습니다. 다시 시도하세요.'


def test_status_sqlite_error_is_korean_error(ready, monkeypatch):
    def broken(*a):
        raise sqlite3.OperationalError('no such table')
    monkeypatch.setattr(stage8.pipeline, '_confirmed_matches', broken)
    with pytest.raises(sessions.StoreError) as exc:
        stage8.persona_status(ready[0].sid)
    assert exc.value.status < 500
    assert exc.value.kind == 'evidence_unavailable'
    assert '근거' in str(exc.value)


@pytest.mark.parametrize('big', [None, 10])
def test_qa_has_exactly_one_failed_card_and_keeps_blocked_persona(big):
    from app.persona.prescribe import prescribe
    from tests.fixtures.evidence_package import PROJECT_CONTEXT
    package = Package.model_validate(make_package(big_persona_contexts=big, qa_failed_persona=3))
    results = [generate_card('qa', b, run_task=FakeBackend().run) for b in package.personas]
    assert [i for i, r in enumerate(results) if r.status == 'failed'] == [3]
    prescriptions = [prescribe('qa', r.card, PROJECT_CONTEXT, run_task=FakeBackend().run)
                     for r in results if r.card]
    assert [r['blocked'] for r in prescriptions] == [True, False, False]


def test_echo_derive_uses_only_supplied_ids():
    from app.llm.base import LLMTask, Attachment
    from app.persona.insights import DeriveOut
    ids = ['other-P8-C7', 'other-P9-C8']
    result = FakeBackend().run(LLMTask(task='insight.derive', sid='qa', instructions='derive',
        attachments=[Attachment(title='input', body=json.dumps({'contexts':[{'context_id':cid} for cid in ids]}))], output_schema=DeriveOut))
    assert result.ok
    assert len(result.data.items) == 3
    assert all(set(item.context_ids) <= set(ids) for item in result.data.items)


def test_echo_multi_persona_concept(ready):
    from app.persona.concepts import make_concept
    session, store, rows, _ = ready
    rows[2]['context_ids'] = ['CL0-P0-C2', 'CL0-P1-C0']
    store.new_revision('insights', rows, by='test', message=None)
    result = make_concept(session.sid, session.version, 'I3', run_task=FakeBackend().run)
    assert {row['context_id'] for row in result['journey']} == set(rows[2]['context_ids'])
    assert all(':' in row['evidence_number'] for row in result['pain_points'])


def test_status_sqlite_error_during_stale_check(ready, monkeypatch):
    def broken(*a):
        raise sqlite3.OperationalError('unable to open database')
    monkeypatch.setattr(stage8.pipeline, 'mark_stale_if_changed', broken)
    with pytest.raises(sessions.StoreError) as exc:
        stage8.persona_status(ready[0].sid)
    assert exc.value.status == 409
    assert exc.value.kind == 'evidence_unavailable'


def test_explicit_fake_response_keeps_parse_error_contract():
    from app.llm.base import LLMTask
    from app.persona.cards import CardOut
    task = LLMTask(task='persona.card', sid='qa', instructions='card', attachments=[], output_schema=CardOut)
    assert FakeBackend({'persona.card': 'not json'}).run(task).error.kind == 'parse'
