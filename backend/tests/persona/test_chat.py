"""Chat validation, append-only history, and resumable serialized insight work."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from threading import Event
from types import SimpleNamespace

import pytest

from app.context import store as sessions
from app.llm.fake import FakeBackend
from app.persona import chat, insight_pipeline
from app.persona.concepts import make_concept
from app.persona.insights import derive
from app.work import worker
from tests.persona.test_insights import env, Embedder
from tests.fixtures.evidence_package import fake_persona_backend
from app.persona.package import load_package


@pytest.fixture
def ready(env, monkeypatch):
    session, store, rows, _ = env
    from app.config import settings
    monkeypatch.setattr(settings, 'embed_backend', 'fake')
    monkeypatch.setattr(chat, 'get_embedder', lambda: Embedder())
    monkeypatch.setattr(insight_pipeline, 'get_embedder', lambda: Embedder())
    backend = FakeBackend(responses=fake_persona_backend(load_package(session.sid, session.version)).responses)
    derive(session.sid, session.version, run_task=backend.run, embedder=Embedder())
    sessions.update_session(session.sid, {'persona': {'status': 'done'}})
    return session, store, rows, backend


def edit(ready, value, target='insights'):
    session = ready[0]
    return chat.edit(session.sid, session.version, target, '더 구체적으로',
        run_task=FakeBackend(responses={'insight.edit': json.dumps(value)}).run)


def test_valid_edit_revision_history(ready):
    session, store, rows, _ = ready
    before = store.read('insights')
    rows[0]['title'] = '새 제목'
    seen = []
    def run(task):
        seen.append(json.loads(task.attachments[0].body))
        return FakeBackend(responses={'insight.edit': json.dumps({'items': rows})}).run(task)
    assert chat.edit(session.sid, session.version, 'insights', '수정', run_task=run) == {'ok': True, 'revision': 2}
    current = store.read('insights')
    assert current['history'][0] == before['history'][0]
    assert current['history'][-1]['by'] == 'chat'
    assert current['history'][-1]['message'] == '수정'
    assert current['history'][-1]['at']
    assert seen[0]['current'] == before and seen[0]['message'] == '수정'
    assert sessions.load_session(session.sid)['insight']['revision'] == 2


@pytest.mark.parametrize('value', [{}, {'items': []}, {'items': [{'title': 1}]}])
def test_invalid_schema_keeps_revision(ready, value):
    before = ready[1].read('insights')
    assert edit(ready, value) == {'ok': False, 'message': '요청을 반영하지 못했습니다. 다르게 말해 주세요.'}
    assert ready[1].read('insights') == before


def test_edit_unknown_context_rejected(ready):
    before = ready[1].read('insights')
    ready[2][0]['context_ids'] = ['missing']
    assert not edit(ready, {'items': ready[2]})['ok']
    assert ready[1].read('insights') == before


def test_codes_recomputed_after_edit(ready):
    rows = ready[2]
    rows[0].update(context_ids=['CL0-P0-C1'], odi=999, radar={'raw': 999})
    assert edit(ready, {'items': rows})['ok']
    items = ready[1].read('insights')['items']
    assert items[0]['odi'] == pytest.approx(.75)
    assert items[0]['radar']['raw'] == dict(Computed=0, Connected=1, Shared=0)
    assert items[0]['opportunity_mean'] == pytest.approx((.75+.75+1.36)/3)


def concept(ready):
    session, store, _, backend = ready
    draft = json.loads(backend.responses['insight.concept'])
    draft['pain_points'] = ['E2', 'E3', 'E4']
    backend.responses['insight.concept'] = json.dumps(draft)
    make_concept(session.sid, session.version, 'I1', run_task=backend.run)
    return draft


@pytest.mark.parametrize('bad', ['cite', 'context'])
def test_bad_cite_rejected(ready, bad):
    draft = concept(ready)
    before = ready[1].read('concepts')
    if bad == 'cite':
        draft['pain_points'][0] = 'E9999'
    else:
        draft['journey'][0]['context_id'] = 'CL0-P0-C1'
    assert not edit(ready, draft, 'concept:I1')['ok']
    assert ready[1].read('concepts') == before


def test_concept_edit_hydrates_source_and_basis(ready):
    draft = concept(ready)
    draft['persona_profile'] = '수정된 프로필'
    ready[3].responses['insight.edit'] = json.dumps(draft)
    session, store, _, backend = ready
    assert chat.edit(session.sid, session.version, 'concept:I1', '수정', run_task=backend.run)['ok']
    item = store.read('concepts')['items'][0]
    assert item['persona_profile']['text'] == '수정된 프로필'
    assert item['basis'] == '근거 4건 · 작성자 2명에서 종합'
    assert item['pain_points'][0]['quote']
    assert sum(item['cx_4d_distribution'].values()) == len(item['journey'])


def test_revert_creates_revision(ready):
    session, store, rows, _ = ready
    first = store.read('insights')['items']
    rows[0]['title'] = '변경'
    edit(ready, {'items': rows})
    assert chat.revert(session.sid, session.version, 'insights', 1) == {'revision': 3}
    assert store.read('insights')['items'] == first
    assert len(store.read('insights')['history']) == 3
    assert sessions.load_session(session.sid)['insight']['revision'] == 3


def test_chat_jsonl_appended(ready):
    edit(ready, {'items': ready[2]})
    edit(ready, {})
    rows = [json.loads(line) for line in (ready[1].path / 'chat.jsonl').read_text().splitlines()]
    assert len(rows) == 2
    assert [r['ok'] for r in rows] == [True, False]
    assert all(r['message'] == '더 구체적으로' and r['target'] == 'insights' and r['at'] for r in rows)


def context(ready, **args):
    session = ready[0]
    return SimpleNamespace(sid=session.sid, version=session.version, args=args,
        run_id='work', should_stop=lambda: False, heartbeat=lambda *a: None)


def test_worker_derive_resume(ready, monkeypatch):
    session, store, _, backend = ready
    calls = []
    monkeypatch.setattr(insight_pipeline.registry, 'run_task', lambda task: calls.append(task.task) or backend.run(task))
    ctx = context(ready, mode='derive')
    insight_pipeline.run(ctx)
    assert calls == []  # durable derived revision is the checkpoint
    assert 'insight' in worker.KINDS
    assert sessions.load_session(session.sid)['insight']['status'] == 'done'


def test_worker_concept_resume_after_stop(ready, monkeypatch):
    concept(ready)
    backend = ready[3]
    draft = json.loads(backend.responses['insight.concept'])
    def run(task):
        if task.task == 'insight.concept':
            payload = json.loads(task.attachments[0].body)
            draft['journey'][0]['context_id'] = payload['insight']['context_ids'][0]
            draft['pain_points'] = list(payload['evidence'])[:3]
            backend.responses['insight.concept'] = json.dumps(draft)
        return backend.run(task)
    monkeypatch.setattr(insight_pipeline.registry, 'run_task', run)
    ctx = context(ready, mode='concept', target=['I1', 'I2', 'I3'])
    ctx.should_stop = lambda: len(ready[1].read('concepts')['items']) >= 2
    insight_pipeline.run(ctx)
    assert sessions.load_session(ctx.sid)['insight']['status'] == 'interrupted'
    first = deepcopy(ready[1].read('concepts')['items'])
    ctx.should_stop = lambda: False
    insight_pipeline.run(ctx)
    assert ready[1].read('concepts')['items'][:2] == first
    assert len(ready[1].read('concepts')['items']) == 3
    assert sessions.load_session(ctx.sid)['insight']['status'] == 'done'


def test_concurrent_runs_serialized(ready, monkeypatch):
    session, store, _, backend = ready
    (store.path / 'insights.json').unlink()
    entered, release = Event(), Event()
    calls = []
    def run(task):
        calls.append(task.task)
        entered.set()
        assert release.wait(5)
        return backend.run(task)
    monkeypatch.setattr(insight_pipeline.registry, 'run_task', run)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(insight_pipeline.run, context(ready, mode='derive'))
        assert entered.wait(5)
        second = pool.submit(insight_pipeline.run, context(ready, mode='derive'))
        release.set()
        first.result(timeout=10)
        second.result(timeout=10)
    assert calls == ['insight.derive']
    assert store.read('insights')['revision'] == 1


def test_concurrent_edits_read_latest_revision(ready):
    session, store, _, _ = ready
    def run(task):
        payload = json.loads(task.attachments[0].body)
        rows = payload['current']['items']
        rows[0]['title'] += '!'
        return FakeBackend(responses={'insight.edit': json.dumps({'items': rows})}).run(task)
    before = store.read('insights')['items'][0]['title']
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(chat.edit, session.sid, session.version, 'insights', '추가', run_task=run)
                   for _ in range(2)]
        assert sorted(f.result(timeout=10)['revision'] for f in futures) == [2, 3]
    assert store.read('insights')['items'][0]['title'] == before + '!!'


def test_revert_one_concept_preserves_other_concepts(ready):
    concept(ready)
    session, store, _, _ = ready
    first = store.read('concepts')['items'][0]
    other = {**deepcopy(first), 'id': 'I2', 'insight_id': 'I2'}
    changed = {**deepcopy(first), 'basis': 'changed'}
    store.new_revision('concepts', [changed, other], by='chat', message='수정')
    assert chat.revert(session.sid, session.version, 'concept:I1', 1) == {'revision': 3}
    items = {row['id']: row for row in store.read('concepts')['items']}
    assert items == {'I1': first, 'I2': other}


@pytest.mark.parametrize('kind', ['backend', 'timeout', 'schema'])
def test_worker_failure_status_and_resume(ready, monkeypatch, kind):
    from app.llm.base import failure
    session, store, _, backend = ready
    (store.path / 'insights.json').unlink()
    monkeypatch.setattr(insight_pipeline.registry, 'run_task', lambda task: failure(kind, 'unavailable'))
    with pytest.raises(BaseException):
        insight_pipeline.run(context(ready, mode='derive'))
    state = sessions.load_session(session.sid)['insight']
    assert state['status'] == ('failed' if kind == 'schema' else 'interrupted')
    if kind != 'schema':
        assert state['reason'] == 'LLM이 연결되지 않았거나 한도를 넘었습니다. 연결을 확인한 뒤 이어서 진행하세요.'
    assert store.read('insights') is None
    monkeypatch.setattr(insight_pipeline.registry, 'run_task', backend.run)
    insight_pipeline.run(context(ready, mode='derive'))
    assert store.read('insights')['revision'] == 1
    state = sessions.load_session(session.sid)['insight']
    assert state['status'] == 'done' and state['savedAt'] and state['confirmed'] == []


def test_worker_requires_persona(ready):
    sessions.update_session(ready[0].sid, {'persona': {'status': 'running'}})
    with pytest.raises(sessions.StoreError) as exc:
        insight_pipeline.run(context(ready, mode='derive'))
    assert exc.value.kind == 'persona_required'
