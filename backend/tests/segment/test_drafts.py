import json

import numpy as np
import pytest

from app.config import settings
from app.llm import registry
from app.llm.base import failure
from app.llm.fake import FakeBackend
from app.segment import drafts
from app.segment.store import SegmentStore


@pytest.fixture
def case(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'llm_backend', 'fake')
    monkeypatch.setattr(settings, 'llm_backend_overrides', {})
    monkeypatch.setattr(settings, 'embed_backend', 'fake')
    store = SegmentStore(tmp_path)
    store.write_layers(
        clusters=[dict(cluster_id='CL0', keywords=[f'word{i}' for i in range(12)],
                       reps=[{'text': f'rep{i}'} for i in range(7)], quality={'flags': ['existing']})],
        personas=[dict(persona_id='CL0-P0', cluster_id='CL0', centrality=[[str(i), 1] for i in range(20)], reps=[{'text': 'persona rep'}])],
        contexts=[dict(context_id='CL0-P0-C0', persona_id='CL0-P0', keywords=['예약'], dominant_constraint='시간', flags=['existing'])],
        docs=[dict(doc_id='d1', cluster_id='CL0', persona_id='CL0-P0', context_id='CL0-P0-C0')])
    context = {'oneLiner': '편안한 냉방 경험', 'targetScope': {'note': '대상힌트'}}
    return store, context


def run(case):
    return drafts.generate_drafts('sid', *case, context_reps={'CL0-P0-C0': [{'text': 'context rep'}]})


def test_cluster_name_draft(case):
    run(case)
    row = case[0].clusters()[0]
    assert row['name_draft'] == '쾌적한 냉방과 절전'
    assert len(row['name_draft']) <= 15
    assert row['name'] is None and row['confirmed_at'] is None


def test_persona_draft_fields(case):
    run(case)
    row = case[0].personas()[0]
    assert row['name_draft'] == '전기료를 살피는 사용자'
    assert row['desire_draft'] == '전기료 부담 없이 시원하게 지내고 싶다.'
    assert len(row['goals_draft']) == 2
    assert row['desire'] is None and row['goals'] is None


def test_context_draft_fields(case):
    run(case)
    row = case[0].contexts()[0]
    assert row['name_draft'] == '잠들기 전 예약 냉방'
    assert row['action_draft'] == '잠들기 전에 에어컨의 온도와 종료 시간을 설정한다.'
    assert row['flags'] == ['existing']
    assert row['action'] is None


def test_persona_prompt_has_target_scope_hint_only(case, monkeypatch):
    tasks = []
    def capture(task):
        tasks.append(task)
        return FakeBackend().run(task)
    monkeypatch.setattr(registry, 'run_task', capture)
    run(case)
    assert [t.task for t in tasks] == ['segment.cluster_name', 'segment.persona_draft', 'segment.context_draft']
    for task in tasks:
        body = '\n'.join(a.body for a in task.attachments)
        assert body.splitlines()[0] == case[1]['oneLiner']
        assert ('targetScope' in body) == (task.task == 'segment.persona_draft')
        assert ('대상힌트' in body) == (task.task == 'segment.persona_draft')
    assert 'word9' in tasks[0].attachments[0].body
    assert 'word10' not in tasks[0].attachments[0].body
    assert 'rep4' in tasks[0].attachments[0].body and 'rep5' not in tasks[0].attachments[0].body
    assert 'context rep' in tasks[2].attachments[0].body
    assert '전기료 부담 없이' in tasks[2].attachments[0].body


@pytest.mark.parametrize('exception', [False, True])
def test_draft_failure_leaves_empty(case, monkeypatch, exception):
    calls = []
    def fail(task):
        calls.append(task.task)
        if exception:
            raise RuntimeError('offline')
        return failure('backend', 'offline')
    monkeypatch.setattr(registry, 'run_task', fail)
    result = run(case)
    assert len(calls) == 3
    assert all(flags == ['draft_failed'] for flags in result['flags'].values())
    store = case[0]
    assert store.clusters()[0]['name_draft'] == ''
    assert store.clusters()[0]['quality']['flags'] == ['existing', 'draft_failed']
    assert store.personas()[0]['desire_draft'] == ''
    assert store.personas()[0]['goals_draft'] == []
    assert store.contexts()[0]['action_draft'] == ''
    assert store.contexts()[0]['flags'] == ['existing', 'draft_failed']
    with store._db() as db:
        assert json.loads(db.execute("SELECT value FROM meta WHERE key='draft_flags'").fetchone()[0]) == result['flags']
    assert len(store.docs()) == 1


def test_persona_draft_clamps(case, monkeypatch):
    backend = FakeBackend(responses={
        'segment.cluster_name': json.dumps({'name': '가' * 20}),
        'segment.persona_draft': json.dumps({'name': '사용자', 'desire': '첫 문장. 둘째 문장! 셋째 문장?', 'goals': ['a', 'b', 'c', 'd', 'e']}),
        'segment.context_draft': json.dumps({'name': '상황', 'action': '설정한다.'})})
    monkeypatch.setattr(registry, 'get_backend', lambda _: backend)
    run(case)
    assert case[0].personas()[0]['desire_draft'] == '첫 문장.'
    assert case[0].personas()[0]['goals_draft'] == ['a', 'b', 'c']
    assert case[0].clusters()[0]['name_draft'] == '가' * 15


@pytest.mark.parametrize('name,model', [('cluster_name', drafts.ClusterNameOut), ('persona_draft', drafts.PersonaDraftOut), ('context_draft', drafts.ContextDraftOut)])
def test_committed_fixture_matches_real_schema(name, model):
    model.model_validate_json((FakeBackend.fixture_dir / f'segment.{name}.json').read_text())


def test_desire_similarity_cross_cluster_only(case, monkeypatch):
    store = case[0]
    rows = [dict(persona_id=f'P{i}', cluster_id=cluster, desire_draft=str(i), similar=[{'id': 'stale'}])
            for i, cluster in enumerate(['A', 'A', 'B', 'C', 'D', 'E'])]
    store.write_layers(personas=rows)
    class Embedder:
        def embed(self, texts):
            assert texts == ['0', '1', '2', '3', '4', '5']
            return np.array([[2, 0], [1, 0], [.85, np.sqrt(1-.85**2)], [0, 1], [0, 0], [np.nan, 0]])
    monkeypatch.setattr(drafts, 'get_embedder', lambda: Embedder())
    drafts.update_desire_similarity(store)
    result = store.personas()
    assert [badge['id'] for badge in result[0]['similar']] == ['P2']
    assert result[0]['similar'][0]['score'] == pytest.approx(.85)
    assert result[0]['similar'][0]['desire'] == '2'
    assert [badge['id'] for badge in result[2]['similar']] == ['P0', 'P1']
    assert all(row['similar'] == [] for row in result[3:])
    assert [row['persona_id'] for row in result] == [row['persona_id'] for row in rows]


def test_rerun_preserves_confirmations_and_clears_failure(case, monkeypatch):
    store = case[0]
    store.confirm('clusters', 'CL0', {'name': '확정 이름'})
    store.confirm('personas', 'CL0-P0', {'name': '확정 인물', 'desire': '확정 욕구', 'goals': ['확정 목표']})
    store.confirm('contexts', 'CL0-P0-C0', {'name': '확정 상황', 'action': '확정 행동'})
    before = store.personas()[0]['confirmed_at']
    with monkeypatch.context() as patch:
        patch.setattr(registry, 'run_task', lambda _: failure('schema', 'invalid'))
        run(case)
    assert all(not flags for flags in run(case)['flags'].values())
    assert store.clusters()[0]['quality']['flags'] == ['existing']
    assert store.contexts()[0]['flags'] == ['existing']
    assert store.clusters()[0]['name'] == '확정 이름'
    assert store.personas()[0]['desire'] == '확정 욕구'
    assert store.personas()[0]['goals'] == ['확정 목표']
    assert store.personas()[0]['confirmed_at'] == before
    assert store.contexts()[0]['action'] == '확정 행동'


def test_similarity_failure_clears_stale_badges(case, monkeypatch):
    store = case[0]
    store.write_layers(personas=[dict(persona_id=str(i), cluster_id=str(i), desire_draft='욕구', similar=[{'id': 'stale'}]) for i in range(2)])
    def fail():
        raise RuntimeError('offline')
    monkeypatch.setattr(drafts, 'get_embedder', fail)
    assert drafts.update_desire_similarity(store) == {'failed': True}
    assert all(row['similar'] == [] for row in store.personas())


def test_persona_clamps_sentences_without_spaces():
    result = drafts.PersonaDraftOut(name='이름', desire='쉬고 싶다.자고 싶다!먹고 싶다?', goals=['목표'])
    assert result.desire == '쉬고 싶다.'
