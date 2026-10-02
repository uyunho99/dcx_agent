"""8-F generation: code-owned evidence, bounded repair, and revision safety."""
from copy import deepcopy
import json
import sqlite3

import pytest

from app.context import store as sessions
from app.context.versions import version_dir
from app.llm import registry
from app.llm.base import failure
from app.llm.fake import FakeBackend
from app.persona import prescribe as prescriptions
from app.segment.store import SegmentStore
from app.persona.concepts import ConceptError, make_concept
from app.persona.package import load_package, evidence_index
from app.persona.prescribe import PrescriptionError
from app.persona.store import PersonaStore
from tests.fixtures.evidence_package import CONSTRAINT, fake_persona_backend, write_session_with_package


@pytest.fixture
def case(data_dir):
    session = write_session_with_package(data_dir)
    store = PersonaStore.open(session.sid, session.version)
    store.write('insights', {'revision': 1, 'items': [dict(id='I1', title='개선',
        pain_point='조절이 번거롭다', context_ids=['CL0-P0-C0'], known_ki_id=None)]})
    return session, store


def runner(case, monkeypatch, *, drafts=None, verdicts=('ok',), check_rows=None):
    session, _ = case
    backend = fake_persona_backend(load_package(session.sid, session.version))
    default = json.loads(backend.responses['insight.concept'])
    default['pain_points'] = ['E2', 'E3', 'E4']
    calls = []
    drafts = [default] if drafts is None else drafts
    counts = {'insight.concept': 0, 'persona.constraint_check': 0}

    def run(task):
        calls.append(task)
        index = counts[task.task]
        counts[task.task] += 1
        if task.task == 'insight.concept':
            value = drafts[min(index, len(drafts)-1)]
        else:
            value = {'constraints': check_rows if check_rows is not None else [dict(
                constraint=CONSTRAINT, verdict=verdicts[min(index, len(verdicts)-1)], reason='검사 결과')]}
        return FakeBackend(responses={task.task: json.dumps(value, ensure_ascii=False)}).run(task)

    monkeypatch.setattr(registry, 'get_backend', lambda name: type('Backend', (), {'run': staticmethod(run)})())
    return registry.run_task, calls, default


def generate(case, run):
    session, _ = case
    return make_concept(session.sid, session.version, 'I1', run_task=run)


def test_profile_always_speculated(case, monkeypatch):
    run, calls, _ = runner(case, monkeypatch)
    result = generate(case, run)
    assert result['persona_profile']['grade'] == 'speculated'
    assert result['persona_profile']['label'] == '합성값'
    assert result['persona_profile']['text']
    assert all(row['service_grade'] == 'prescription' and row['service_label'] == '처방'
               for row in result['journey'])
    assert 'basis' not in calls[0].output_schema.model_fields


def test_basis_filled_by_code(case, monkeypatch):
    session, _ = case
    path = version_dir(session.sid, session.version) / 'evidence/package.json'
    package = sessions.read_json(path)
    package['personas'][0]['context_evidence'][0]['metrics'].update(doc_count=45, author_count=26)
    sessions.write_json(path, package)
    run, _, _ = runner(case, monkeypatch)
    assert generate(case, run)['basis'] == '근거 4건 · 작성자 0명에서 종합'


def test_pain_points_from_package(case, monkeypatch):
    run, _, _ = runner(case, monkeypatch)
    result = generate(case, run)
    session, _ = case
    refs = evidence_index(load_package(session.sid, session.version).personas[0])
    assert len(result['pain_points']) == 3
    for point in result['pain_points']:
        ref = refs[point['evidence_number']]
        assert point['quote'] == ref.quote.text
        assert point['channel'] == ref.source
        assert point['location'] == {k: getattr(ref.quote, k) for k in ('field', 'idx', 'start', 'end')}
        assert point['context_id'] == ref.context_id
        assert point['doc_id'] == ref.doc_id
        assert point['verified'] == ref.verified


def test_asis_context_validation_regen_once(case, monkeypatch):
    _, _, good = runner(case, monkeypatch)
    bad = deepcopy(good)
    bad['journey'][0]['context_id'] = 'CL0-P0-C1'  # Exists in package, outside insight.
    run, calls, _ = runner(case, monkeypatch, drafts=[bad, good])
    assert generate(case, run)['journey'][0]['context_id'] == 'CL0-P0-C0'
    assert [t.task for t in calls].count('insight.concept') == 2
    run, calls, _ = runner(case, monkeypatch, drafts=[bad])
    previous = case[1].read('concepts')
    with pytest.raises(ConceptError):
        generate(case, run)
    assert [t.task for t in calls].count('insight.concept') == 2
    assert case[1].read('concepts') == previous


def test_cx4d_distribution(case, monkeypatch):
    _, _, draft = runner(case, monkeypatch)
    draft['journey'] = [{**draft['journey'][0], 'cx_4d': axis}
                        for axis in ['정신적', '시스템', '시스템', '물리적']]
    run, _, _ = runner(case, monkeypatch, drafts=[draft])
    assert generate(case, run)['cx_4d_distribution'] == {'정신적': 1, '물리적': 1, '문화적': 0, '시스템': 2}


@pytest.mark.parametrize('verdicts,blocked', [(('ok',), False), (('review',), False),
    (('violates', 'ok'), False), (('violates', 'violates'), True)])
def test_constraint_check_reused(case, monkeypatch, verdicts, blocked):
    run, calls, _ = runner(case, monkeypatch, verdicts=verdicts)
    result = generate(case, run)
    assert [t.task for t in calls] == ['insight.concept', 'persona.constraint_check'] * len(verdicts)
    assert result['blocked'] is blocked
    assert result['represcribed'] is (len(verdicts) == 2)
    assert result['constraint_check'][0]['verdict'] == verdicts[-1]
    checked = json.loads(calls[1].attachments[0].body)
    assert checked['constraints'] == [CONSTRAINT]
    assert checked['prescription']['journey'] == result['journey']
    if blocked:
        assert result['message'] == "사내 제약 '의료적 효과 표현 금지'를 지키는 처방을 만들지 못했습니다."


@pytest.mark.parametrize('rows', [[], [dict(constraint='unknown', verdict='ok', reason='ok')]])
def test_incomplete_check_does_not_save(case, monkeypatch, rows):
    run, _, _ = runner(case, monkeypatch, check_rows=rows)
    with pytest.raises(PrescriptionError):
        generate(case, run)
    assert case[1].read('concepts') is None


@pytest.mark.parametrize('field,value', [('pain_points', ['E999', 'E2', 'E3']),
                                        ('pain_points', ['E2', 'E3'])])
def test_invalid_evidence_not_saved(case, monkeypatch, field, value):
    _, _, draft = runner(case, monkeypatch)
    draft[field] = value
    run, _, _ = runner(case, monkeypatch, drafts=[draft])
    with pytest.raises(ConceptError):
        generate(case, run)
    assert case[1].read('concepts') is None


def test_revision_preserves_other_concepts(case, monkeypatch):
    store = case[1]
    store.new_revision('concepts', [{'insight_id': 'other', 'id': 'other'}], by='generate', message=None)
    run, _, _ = runner(case, monkeypatch)
    first = generate(case, run)
    second = generate(case, run)
    saved = store.read('concepts')
    assert first['revision'] == 2 and second['revision'] == 3
    assert len(saved['items']) == 2
    assert saved['items'][0] == {'insight_id': 'other', 'id': 'other'}
    assert len(saved['history']) == 3


@pytest.mark.parametrize('name', ['insight.concept', 'persona.constraint_check'])
def test_failed_call_preserves_revision(case, monkeypatch, name):
    run, _, _ = runner(case, monkeypatch)
    generate(case, run)
    previous = case[1].read('concepts')
    def fail(task):
        return failure('backend', 'unavailable') if task.task == name else run(task)
    with pytest.raises((ConceptError, PrescriptionError)):
        generate(case, fail)
    assert case[1].read('concepts') == previous


def test_multiple_personas_keep_evidence_namespaces(case, monkeypatch):
    session, store = case
    insights = store.read('insights')
    insights['items'][0]['context_ids'] = ['CL0-P0-C0', 'CL0-P1-C0', 'CL0-P0-C0']
    store.write('insights', insights)
    _, _, draft = runner(case, monkeypatch)
    draft['pain_points'] = ['CL0-P0:E2', 'CL0-P1:E2', 'CL0-P1:E3']
    run, _, _ = runner(case, monkeypatch, drafts=[draft])
    result = generate(case, run)
    refs = evidence_index(load_package(session.sid, session.version).personas[1])
    assert result['pain_points'][1]['doc_id'] == refs['E2'].doc_id
    assert result['pain_points'][1]['context_id'] == 'CL0-P1-C0'
    assert result['basis'] == '근거 8건 · 작성자 0명에서 종합'


@pytest.mark.parametrize('mutation', ['cx_4d', 'profile_grade'])
def test_schema_rejects_invalid_values(case, monkeypatch, mutation):
    _, _, draft = runner(case, monkeypatch)
    if mutation == 'cx_4d':
        draft['journey'][0]['cx_4d'] = '경제적'
    elif mutation == 'basis':
        draft['basis'] = '근거 999건'
    else:
        draft['persona_profile'] = {'text': '합성', 'grade': 'observed'}
    run, calls, _ = runner(case, monkeypatch, drafts=[draft])
    with pytest.raises(ConceptError):
        generate(case, run)
    assert len(calls) == 2  # Registry schema retry, never a saved concept.
    assert case[1].read('concepts') is None


def test_unknown_insight_context_rejected_before_llm(case):
    store = case[1]
    insights = store.read('insights')
    insights['items'][0]['context_ids'] = ['unknown']
    store.write('insights', insights)
    def unexpected(task):
        pytest.fail('LLM called for invalid input')
    with pytest.raises(ConceptError):
        generate(case, unexpected)
    assert store.read('concepts') is None


def test_empty_constraints(case, monkeypatch):
    sessions.update_session(case[0].sid, {'projectContext': {'constraints': []}})
    run, _, _ = runner(case, monkeypatch, check_rows=[])
    result = generate(case, run)
    assert result['constraint_check'] == []
    assert not result['blocked']


def test_shared_fixture_response_supported(case):
    session, _ = case
    backend = fake_persona_backend(load_package(session.sid, session.version))
    result = generate(case, backend.run)
    assert result['blocked'] is True
    assert result['represcribed'] is True
    assert result['pain_points'][0]['evidence_number'] == 'E1'


def test_basis_counts_distinct_authors(case, monkeypatch):
    session, store = case
    insights = store.read('insights')
    insights['items'][0]['context_ids'] = ['CL0-P0-C0', 'CL0-P0-C1', 'CL0-P0-C0']
    store.write('insights', insights)
    path = version_dir(session.sid, session.version) / 'evidence/package.json'
    package = sessions.read_json(path)
    first, second = package['personas'][0]['context_evidence'][:2]
    # Duplicate across roles and Contexts; desire-only evidence is excluded.
    second['evidence'].append(deepcopy(first['evidence'][0]))
    first['counter_evidence'].append(deepcopy(first['evidence'][0]))
    package['personas'][0]['persona_evidence']['desire_support'][0]['doc_id'] = 'desire-only'
    sessions.write_json(path, package)
    with sqlite3.connect(SegmentStore.open(session.sid, session.version).path) as db:
        db.execute('DELETE FROM docs')
        db.executemany('INSERT INTO docs (doc_id, author_hash) VALUES (?, ?)', [
            ('d000000', 'shared'), ('d000001', None), ('d000002', 'counter'),
            ('d000003', 'rare'), ('d000008', 'shared'), ('d000009', None),
            ('d000010', 'counter'),  # d000011 is missing; still counts as evidence.
            ('desire-only', 'excluded'), ('unrelated', 'excluded-too')])
    run, _, _ = runner(case, monkeypatch)
    assert generate(case, run)['basis'] == '근거 8건 · 작성자 3명에서 종합'


def test_concept_uses_public_constraint_check(case, monkeypatch):
    run, calls, _ = runner(case, monkeypatch)
    checked = []

    def check(sid, text, project_context, *, run_task):
        checked.append((sid, text, project_context, run_task))
        return [dict(constraint=CONSTRAINT, verdict='review', reason='public check')]

    monkeypatch.setattr(prescriptions, 'check_constraints', check)
    result = generate(case, run)
    assert [task.task for task in calls] == ['insight.concept']
    assert checked[0][0] == case[0].sid
    assert checked[0][1]['journey'] == result['journey']
    assert checked[0][2]['constraints'] == [CONSTRAINT]
    assert checked[0][3] is run
    assert result['constraint_check'][0]['reason'] == 'public check'
