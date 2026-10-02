import json

import pytest

from app.context.models import ProjectContext
from app.llm import registry
from app.llm.base import failure
from app.llm.fake import FakeBackend
from app.persona.prescribe import PrescriptionError, prescribe, scope_check
from tests.fixtures.evidence_package import (
    CONSTRAINT, PROJECT_CONTEXT, fake_persona_backend, make_package,
)

SUMMARY = {'persona_id': 'CL0-P0', 'intent': {'text': '편안한 생활을 원한다'}}


def runner(monkeypatch, verdicts=('ok',), *, scope='in'):
    backend = fake_persona_backend(make_package())
    calls = []
    checks = iter(verdicts)

    def run(task):
        calls.append(task)
        responses = dict(backend.responses)
        if task.task == 'persona.constraint_check':
            responses[task.task] = json.dumps({'constraints': [
                {'constraint': CONSTRAINT, 'verdict': next(checks), 'reason': '의료적 효과를 단정함'}
            ]}, ensure_ascii=False)
        elif task.task == 'persona.scope':
            responses[task.task] = json.dumps({'verdict': scope, 'reason': '범위 대조 결과'})
        elif task.task == 'persona.prescribe' and sum(t.task == task.task for t in calls) > 1:
            revised = json.loads(responses[task.task])
            revised['direction'] = '예약 조절을 안내한다'
            responses[task.task] = json.dumps(revised)
        return FakeBackend(responses=responses).run(task)

    monkeypatch.setattr(registry, 'get_backend', lambda name: type('Backend', (), {'run': staticmethod(run)})())
    return registry.run_task, calls


def payload(task):
    return json.loads(task.attachments[0].body)


@pytest.mark.parametrize('final_verdict', ['ok', 'review'])
def test_violation_represcribe_once(monkeypatch, final_verdict):
    run, calls = runner(monkeypatch, ('violates', final_verdict))
    result = prescribe('s', SUMMARY, PROJECT_CONTEXT, run_task=run)
    assert [t.task for t in calls] == ['persona.prescribe', 'persona.constraint_check'] * 2
    retry = payload(calls[2])
    assert retry['violations'] == [{'constraint': CONSTRAINT, 'verdict': 'violates', 'reason': '의료적 효과를 단정함'}]
    assert retry['previous_prescription']['direction'] == '에어컨으로 질병을 치료한다고 안내한다'
    assert payload(calls[3])['prescription']['direction'] == '예약 조절을 안내한다'
    assert result['direction'] == '예약 조절을 안내한다'
    assert result['represcribed'] is True and result['blocked'] is False
    assert result['constraint'][0]['verdict'] == final_verdict


def test_blocked_after_second_violation():
    backend = fake_persona_backend(make_package())
    calls = []

    def run(task):
        calls.append(task)
        return backend.run(task)

    result = prescribe('s', SUMMARY, PROJECT_CONTEXT, run_task=run)
    assert len(calls) == 4
    assert result['blocked'] is True and result['represcribed'] is True
    assert result['message'] == "사내 제약 '의료적 효과 표현 금지'를 지키는 처방을 만들지 못했습니다."
    assert result['constraint'][0]['reason'] == '의료적 효과를 단정함'


@pytest.mark.parametrize('verdict', ['ok', 'review'])
def test_review_not_blocking(monkeypatch, verdict):
    run, calls = runner(monkeypatch, (verdict,))
    result = prescribe('s', SUMMARY, PROJECT_CONTEXT, run_task=run)
    assert result['blocked'] is False and result['represcribed'] is False
    assert result['constraint'][0]['verdict'] == verdict
    assert len(calls) == 2


def test_scope_outside_future(monkeypatch):
    run, calls = runner(monkeypatch, scope='outside')
    result = scope_check('s', SUMMARY, PROJECT_CONTEXT, run_task=run)
    assert result == {'verdict': 'outside', 'reason': '범위 대조 결과'}
    assert len(calls) == 1


def test_scope_separate_call(monkeypatch):
    run, calls = runner(monkeypatch)
    context = ProjectContext.model_validate(PROJECT_CONTEXT)
    prescribe('s', SUMMARY, context, run_task=run)
    assert [t.task for t in calls] == ['persona.prescribe', 'persona.constraint_check']
    assert scope_check('s', SUMMARY, context, run_task=run)['verdict'] == 'in'
    scope = calls[-1]
    assert scope.task == 'persona.scope'
    assert scope.task not in ('persona.card', 'persona.summary')
    assert '카드를 생성' not in scope.instructions
    assert payload(scope) == {'card_summary': SUMMARY, **{k: context.model_dump(mode='json')[k]
                             for k in ('targetScope', 'productCategory', 'positioning')}}
    assert set(payload(calls[0])) == {'card_summary', 'analysisGoal', 'keyMetrics', 'constraints'}
    assert set(payload(calls[1])) == {'prescription', 'constraints'}
    assert all('targetScope' not in t.attachments[0].body for t in calls[:-1])


@pytest.mark.parametrize('name', ['persona.prescribe', 'persona.constraint_check', 'persona.scope'])
def test_failed_call_is_not_a_success(name):
    backend = fake_persona_backend(make_package())

    def run(task):
        return failure('backend', 'unavailable') if task.task == name else backend.run(task)

    operation = scope_check if name == 'persona.scope' else prescribe
    with pytest.raises(PrescriptionError, match=name):
        operation('s', SUMMARY, PROJECT_CONTEXT, run_task=run)


@pytest.mark.parametrize('rows', [[], [dict(constraint='다른 제약', verdict='ok', reason='충족')],
                                  [dict(constraint=CONSTRAINT, verdict='ok', reason='충족')] * 2])
def test_constraint_check_requires_every_constraint_once(rows):
    backend = fake_persona_backend(make_package())

    def run(task):
        if task.task == 'persona.constraint_check':
            return FakeBackend(responses={task.task: json.dumps({'constraints': rows})}).run(task)
        return backend.run(task)

    with pytest.raises(PrescriptionError):
        prescribe('s', SUMMARY, PROJECT_CONTEXT, run_task=run)


def test_empty_constraints():
    backend = fake_persona_backend(make_package())
    context = {**PROJECT_CONTEXT, 'constraints': []}

    def run(task):
        if task.task == 'persona.constraint_check':
            return FakeBackend(responses={task.task: '{"constraints": []}'}).run(task)
        return backend.run(task)

    result = prescribe('s', SUMMARY, context, run_task=run)
    assert result['constraint'] == []
    assert not result['blocked'] and not result['represcribed']


@pytest.mark.parametrize('name, raw', [
    ('persona.prescribe', '{"direction": 42}'),
    ('persona.constraint_check', '{"constraints": [{"constraint": "의료적 효과 표현 금지", "verdict": "safe", "reason": "충족"}]}'),
    ('persona.scope', '{"verdict": "future", "reason": "범위 밖"}'),
])
def test_invalid_output_fails_after_registry_schema_retry(monkeypatch, name, raw):
    backend = fake_persona_backend(make_package())
    responses = {**backend.responses, name: raw}
    calls = []

    def run(task):
        calls.append(task.task)
        return FakeBackend(responses=responses).run(task)

    monkeypatch.setattr(registry, 'get_backend', lambda task: type('Backend', (), {'run': staticmethod(run)})())
    operation = scope_check if name == 'persona.scope' else prescribe
    with pytest.raises(PrescriptionError, match=name):
        operation('s', SUMMARY, PROJECT_CONTEXT)
    assert calls.count(name) == 2
