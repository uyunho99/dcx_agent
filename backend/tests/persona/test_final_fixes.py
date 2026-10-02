"""Final-review regressions: publication races and stage-eight wire contracts."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import json

import pytest

from app.context import store as sessions
from app.context.versions import version_dir
from app.llm import registry
from app.llm.fake import FakeBackend
from app.persona import chat, insights, insight_pipeline, pipeline
from app.persona.cards import generate_card
from app.persona.package import load_package
from app.routers import stage8
from tests.persona.test_insights import env, Embedder
from tests.persona.test_chat import ready, edit, concept, context
from tests.persona.test_pipeline import setup
from tests.persona.test_cards import setup as cards_setup


@pytest.mark.parametrize('operation', ['write', 'new_revision', 'revert', 'append_chat'])
def test_store_rechecks_writable_inside_lock(ready, monkeypatch, operation):
    session, store, _, _ = ready
    before = store.read('insights')
    locked = False
    original = sessions.locked
    @contextmanager
    def switched(sid):
        nonlocal locked
        with original(sid):
            locked = True
            try:
                yield
            finally:
                locked = False
    def writable(*args):
        if locked:
            raise sessions.StoreError('read only')
        return sessions.load_session(session.sid)
    monkeypatch.setattr(sessions, 'locked', switched)
    monkeypatch.setattr(sessions, 'assert_writable', writable)
    actions = dict(write=lambda: store.write('insights', {}),
        new_revision=lambda: store.new_revision('insights', [], by='chat', message=None),
        revert=lambda: store.revert('insights', 1), append_chat=lambda: store.append_chat({'ok': False}))
    with pytest.raises(sessions.StoreError):
        actions[operation]()
    assert store.read('insights') == before
    assert not (store.path / 'chat.jsonl').exists()


def test_concept_source_and_invalidation(ready, monkeypatch):
    concept(ready)
    store = ready[1]
    item = store.read('concepts')['items'][0]
    assert item['insight_revision'] == 1
    assert item['context_ids'] == ready[2][0]['context_ids']
    ready[2][0]['title'] = 'changed source'
    assert edit(ready, {'items': ready[2]})['ok']
    assert store.read('concepts')['items'][0]['outdated'] is True
    called = []
    monkeypatch.setattr(insight_pipeline, 'make_concept', lambda *a, **kw: called.append(a[2]))
    insight_pipeline.run(context(ready, mode='concept', target='I1'))
    assert called == ['I1']


def test_confirmation_survives_roundtrip_revert(ready):
    session, store, rows, _ = ready
    rows[0]['id'] = 'I4'
    assert edit(ready, {'items': rows})['ok']
    insights.confirm(session.sid, session.version, ['I4', 'I2'])
    chat.revert(session.sid, session.version, 'insights', 1)
    assert sessions.load_session(session.sid)['insight']['confirmed'] == ['I2']
    chat.revert(session.sid, session.version, 'insights', 2)
    assert sessions.load_session(session.sid)['insight']['confirmed'] == ['I4', 'I2']


@pytest.mark.parametrize('marker', ['persona', 'stage8'])
@pytest.mark.parametrize('operation', ['chat', 'revert', 'confirm'])
def test_stale_mutations_rejected(ready, marker, operation):
    session, store, rows, _ = ready
    sessions.update_session(session.sid, {'persona': {'status': 'stale'}} if marker == 'persona'
                            else {'stale': {'stage8': 'changed'}})
    before = store.read('insights')
    with pytest.raises(sessions.StoreError) as error:
        if operation == 'chat':
            edit(ready, {'items': rows})
        elif operation == 'revert':
            chat.revert(session.sid, session.version, 'insights', 1)
        else:
            insights.confirm(session.sid, session.version, ['I1'])
    assert error.value.status == 409 and error.value.kind == 'stale'
    assert store.read('insights') == before


def test_worker_does_not_publish_after_source_change(ready, monkeypatch):
    session, store, _, backend = ready
    (store.path / 'insights.json').unlink()
    def changed(task):
        sessions.update_session(session.sid, {'stale': {'stage8': 'changed during inference'}})
        return backend.run(task)
    monkeypatch.setattr(registry, 'run_task', changed)
    with pytest.raises(sessions.StoreError):
        insight_pipeline.run(context(ready, mode='derive'))
    assert store.read('insights') is None


@pytest.mark.parametrize('operation', ['chat', 'derive'])
def test_uses_preparation_embedder(ready, monkeypatch, operation):
    from app.known import store as known
    calls = []
    def resolve(sid, data, factory):
        calls.append((sid, data['version']))
        return Embedder()
    monkeypatch.setattr(known, 'session_embedder', resolve)
    if operation == 'chat':
        assert edit(ready, {'items': ready[2]})['ok']
    else:
        (ready[1].path / 'insights.json').unlink()
        monkeypatch.setattr(registry, 'run_task', ready[3].run)
        insight_pipeline.run(context(ready, mode='derive'))
    assert calls == [(ready[0].sid, ready[0].version)]


@pytest.mark.parametrize('status', ['failed', 'interrupted'])
def test_worker_contract(ready, monkeypatch, status):
    session = ready[0]
    sessions.update_session(session.sid, {'insight': {'status': status, 'reason': 'failure reason',
                             'run': 'work', 'mode': 'concept', 'target': 'I1'}})
    monkeypatch.setattr(stage8.runner, 'status', lambda sid: [])
    assert stage8.get_insights(session.sid)['worker'] == dict(status=status, reason='failure reason',
                                           runId='work', mode='concept', target='I1')


def test_card_package_fields():
    package, runner = cards_setup()
    block = package.personas[0]
    card = generate_card('sid', block, run_task=runner).card
    assert card['artifacts'] == [a.model_dump() for a in block.persona_evidence.artifacts]
    assert [r['keywords'] for r in card['contexts']] == [c.keywords for c in block.context_evidence]


def test_real_registry_card_attempts_and_report(setup, monkeypatch):
    ctx, root, _ = setup
    # Restore the actual registry entry point replaced by the setup fixture.
    from importlib import reload
    reload(registry)
    backend = FakeBackend(responses={'persona.card': '{}'})
    attempts = []
    class Backend:
        def run(self, task):
            attempts.append(task.task)
            return backend.run(task)
    monkeypatch.setattr(registry, 'get_backend', lambda name: Backend())
    pipeline.run(ctx)
    report = sessions.read_json(root / 'persona/stage_8.json')
    assert len(attempts) == 8  # four Persona chunks, exactly two schema attempts each
    assert report['llm_calls']['card'] == len(attempts)


def test_unknown_known_id_is_cleared(ready):
    ready[2][0]['known_ki_id'] = 'invented'
    assert edit(ready, {'items': ready[2]})['ok']
    item = ready[1].read('insights')['items'][0]
    assert item['known_ki_id'] is None and item['known_badge'] is None


def test_cross_kind_launch_is_serialized(ready, monkeypatch):
    session = ready[0]
    cards = ready[1].read('cards')
    cards.update(package_run=load_package(session.sid, session.version).run)
    ready[1].write('cards', cards)
    entered, release = Event(), Event()
    works = []
    def start(sid, version, kind, args):
        if kind == 'persona':
            entered.set()
            assert release.wait(5)
        works.append(dict(kind=kind, version=version, state='running'))
        return {'runId': kind}
    monkeypatch.setattr(stage8.runner, 'status', lambda sid: list(works))
    monkeypatch.setattr(stage8.runner, 'start', start)
    with ThreadPoolExecutor(2) as pool:
        a = pool.submit(stage8.start_persona, session.sid)
        assert entered.wait(5)
        b = pool.submit(stage8.start_insight, session.sid, stage8.InsightRun(mode='derive'))
        try:
            # The second launch must not pass the gate while registration is pending.
            from concurrent.futures import TimeoutError
            with pytest.raises(TimeoutError):
                b.result(timeout=.15)
        finally:
            release.set()
        a.result(timeout=5)
        with pytest.raises(sessions.StoreError):
            b.result(timeout=5)
    assert len(works) == 1


@pytest.mark.parametrize('selected', [None, ['CL0-P0']])
def test_fresh_stale_rebuilds_checkpoints(setup, selected):
    ctx, root, runner = setup
    pipeline.run(ctx)
    old = sessions.read_json(root / 'persona/cards.json')
    package = sessions.read_json(root / 'evidence/package.json')
    package['run'] = 'new-evidence-run'
    sessions.write_json(root / 'evidence/package.json', package)
    assert pipeline.mark_stale_if_changed(ctx.sid, ctx.version)
    before = len(runner.calls)
    ctx.args = {'fresh': True, 'personas': selected}
    pipeline.run(ctx)
    current = sessions.read_json(root / 'persona/cards.json')
    assert current['package_run'] == 'new-evidence-run' and current['run'] != old['run']
    assert sum(t.task == 'persona.card' for t in runner.calls[before:]) == 4
    assert 'stage8' not in sessions.load_session(ctx.sid).get('stale', {})


def test_fresh_reset_cancels_pending_chat(ready, monkeypatch):
    session, store, rows, _ = ready
    entered, release, reset_requested = Event(), Event(), Event()
    original_write = sessions.write_json
    original_load = pipeline.load_package
    def write(path, value):
        original_write(path, value)
        if path.name == 'session.json' and value.get('persona', {}).get('reset_epoch'):
            reset_requested.set()
    def load(*args):
        reset_requested.set()  # old implementation has no reset epoch
        return original_load(*args)
    monkeypatch.setattr(sessions, 'write_json', write)
    monkeypatch.setattr(pipeline, 'load_package', load)
    monkeypatch.setattr(registry, 'run_task', ready[3].run)
    def pending(task):
        entered.set()
        assert release.wait(5)
        return FakeBackend(responses={'insight.edit': json.dumps({'items': rows})}).run(task)
    with ThreadPoolExecutor(2) as pool:
        a = pool.submit(chat.edit, session.sid, session.version, 'insights', 'edit', run_task=pending)
        assert entered.wait(5)
        b = pool.submit(pipeline.run, context(ready, fresh=True))
        try:
            assert reset_requested.wait(5)
        finally:
            release.set()
        assert a.result(timeout=10) == {'ok': False, 'message': chat.FAILURE_COPY}
        b.result(timeout=10)
    assert store.read('insights') is None


def test_status_exposes_package_presence(ready, monkeypatch):
    session = ready[0]
    monkeypatch.setattr(stage8.runner, 'status', lambda sid: [])
    assert stage8.persona_status(session.sid)['package'] is True
    (version_dir(session.sid, session.version) / 'evidence/package.json').unlink()
    assert stage8.persona_status(session.sid)['package'] is False


def test_empty_evidence_skips_llm():
    package, runner = cards_setup()
    block = package.personas[0]
    block.persona_evidence.desire_support = []
    for c in block.context_evidence:
        c.evidence = []
        c.counter_evidence = []
        c.rare_evidence = []
    assert generate_card('sid', block, run_task=runner).status == 'done'
    assert runner.calls == []


def test_concept_ignores_computed_fields(ready):
    draft = concept(ready)
    draft.update(basis='invented', odi=999)
    ready[3].responses['insight.edit'] = json.dumps(draft)
    session = ready[0]
    assert chat.edit(session.sid, session.version, 'concept:I1', 'edit', run_task=ready[3].run)['ok']
    assert ready[1].read('concepts')['items'][0]['basis'] != 'invented'


def test_concept_rejects_duplicate_evidence(ready):
    draft = concept(ready)
    draft['pain_points'] = ['E2'] * 3
    ready[3].responses['insight.edit'] = json.dumps(draft)
    session = ready[0]
    assert not chat.edit(session.sid, session.version, 'concept:I1', 'edit', run_task=ready[3].run)['ok']


def test_suggestions_exclude_already_added(client, monkeypatch):
    from tests.known.test_suggestions import seed
    from app.known import store as known
    monkeypatch.setattr(known, '_embed_many', lambda *args: None)
    seed('previous')
    seed('current', items=[])
    client.post('/known/current', json={'type': 'statement', 'text': 'Title', 'from': 'prev_session'})
    assert known.suggestions('current') == []


def test_completion_reconciles_changed_confirmations(setup):
    from app.routers.sessions import _completion
    from app.segment.store import SegmentStore
    ctx, root, _ = setup
    pipeline.run(ctx)
    import sqlite3
    with sqlite3.connect(SegmentStore.open(ctx.sid, ctx.version).path) as db:
        db.execute("UPDATE personas SET name='changed' WHERE persona_id='CL0-P0'")
    data = sessions.load_session(ctx.sid)
    assert not _completion(ctx.sid, data, ctx.version)['personaDone']


def test_concept_revert_cannot_restore_obsolete_source(ready):
    concept(ready)
    ready[2][0]['context_ids'] = ['CL0-P0-C1']
    assert edit(ready, {'items': ready[2]})['ok']
    session = ready[0]
    chat.revert(session.sid, session.version, 'concept:I1', 1)
    assert ready[1].read('concepts')['items'][0]['outdated'] is True


def test_chat_detects_changed_package_without_poll(ready):
    session, store, _, _ = ready
    package = load_package(session.sid, session.version)
    cards = store.read('cards')
    cards.update(package_run=package.run, package_hash=pipeline._digest(package))
    store.write('cards', cards)
    path = version_dir(session.sid, session.version) / 'evidence/package.json'
    raw = sessions.read_json(path)
    raw['run'] = 'changed'
    sessions.write_json(path, raw)
    with pytest.raises(sessions.StoreError) as exc:
        edit(ready, {'items': ready[2]})
    assert exc.value.kind == 'stale'


def test_dimension_mismatch_has_clear_worker_reason(ready, monkeypatch):
    import numpy as np
    from app.known import store as known
    class WrongDimension:
        def embed(self, texts, input_type=None):
            return np.ones((3, 4))
    monkeypatch.setattr(known, 'session_embedder', lambda *a: WrongDimension())
    monkeypatch.setattr(registry, 'run_task', ready[3].run)
    (ready[1].path / 'insights.json').unlink()
    with pytest.raises(insights.InsightError):
        insight_pipeline.run(context(ready, mode='derive'))
    assert 'dimension' in sessions.load_session(ready[0].sid)['insight']['reason'].lower()
    assert ready[1].read('insights') is None


@pytest.mark.parametrize('status', ['failed', 'interrupted', 'running'])
def test_worker_contract_uses_durable_supervisor(ready, status):
    from app.work.status import transaction
    import os
    import time
    sid = ready[0].sid
    with transaction(sid) as db:
        db.execute('''INSERT INTO runs
            (run_id,version,kind,args_json,pid,state,heartbeat_at,started_at,error)
            VALUES (?,?,?,?,?,?,?,?,?)''', ('durable', 'v1', 'insight',
            json.dumps({'mode': 'concept', 'target': 'I2'}), os.getpid(), status,
            time.time(), time.time(), 'durable failure' if status != 'running' else None))
    result = stage8.get_insights(sid)['worker']
    assert result == dict(status=status, reason='durable failure' if status != 'running' else None,
                         runId='durable', mode='concept', target='I2')


def test_failed_chat_never_appends_to_old_version(ready):
    from app.context.versions import create_version
    session, store, _, _ = ready
    before = store.read('insights')
    def switched(task):
        create_version(session.sid, session.version, 'stage8', '')
        return FakeBackend(responses={'insight.edit': '{}'}).run(task)
    with pytest.raises(sessions.StoreError):
        chat.edit(session.sid, session.version, 'insights', 'edit', run_task=switched)
    assert store.read('insights') == before
    assert not (store.path / 'chat.jsonl').exists()


def test_source_rechecked_after_radar_embedding(ready, monkeypatch):
    from app.known import store as known
    session = ready[0]
    class Changed(Embedder):
        def embed(self, texts, input_type=None):
            sessions.update_session(session.sid, {'stale': {'stage8': 'changed during radar'}})
            return super().embed(texts, input_type)
    monkeypatch.setattr(known, 'session_embedder', lambda *a: Changed())
    monkeypatch.setattr(registry, 'run_task', ready[3].run)
    (ready[1].path / 'insights.json').unlink()
    with pytest.raises(sessions.StoreError) as exc:
        insight_pipeline.run(context(ready, mode='derive'))
    assert exc.value.kind == 'stale'
    assert ready[1].read('insights') is None


@pytest.mark.parametrize('operation', ['chat', 'derive'])
def test_changed_global_backend_does_not_change_preparation_axes(ready, monkeypatch, operation):
    from app.known import store as known
    from app.config import settings
    monkeypatch.setattr(settings, 'embed_backend', 'voyage')
    monkeypatch.setattr(known, 'FakeEmbedder', Embedder)
    def wrong_global():
        pytest.fail('Global embedding provider must not be used for the prepared session')
    monkeypatch.setattr(chat, 'get_embedder', wrong_global)
    monkeypatch.setattr(insight_pipeline, 'get_embedder', wrong_global)
    if operation == 'chat':
        assert edit(ready, {'items': ready[2]})['ok']
    else:
        (ready[1].path / 'insights.json').unlink()
        monkeypatch.setattr(registry, 'run_task', ready[3].run)
        insight_pipeline.run(context(ready, mode='derive'))
    assert ready[1].read('insights')['items'][0]['radar']['raw']['Computed'] == 1


def test_centroid_reader_closes_connection(ready, monkeypatch):
    import sqlite3
    original = sqlite3.connect
    opened = []
    def connect(*args, **kwargs):
        db = original(*args, **kwargs)
        opened.append(db)
        return db
    monkeypatch.setattr(insights.sqlite3, 'connect', connect)
    insights._centroids(ready[0].sid, ready[0].version, ['CL0-P0-C0'])
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        opened[0].execute('SELECT 1')


def test_real_registry_counts_second_attempt_exception(ready, monkeypatch):
    attempts = []
    class Backend:
        def run(self, task):
            attempts.append(task.task)
            if len(attempts) == 2:
                raise ConnectionError('provider disconnected')
            return FakeBackend(responses={'persona.card': '{}'}).run(task)
    monkeypatch.setattr(registry, 'get_backend', lambda name: Backend())
    calls = pipeline._Calls(ready[1].path, lambda: None)
    result = generate_card(ready[0].sid, load_package(ready[0].sid, 'v1').personas[0],
                           run_task=calls.run_task)
    assert result.status == 'failed'
    assert len(attempts) == 2 and calls.counts['card'] == 2


def test_confirm_rejected_while_reset_waits(ready, monkeypatch):
    requested = Event()
    original = sessions.write_json
    def write(path, value):
        original(path, value)
        if path.name == 'session.json' and value.get('persona', {}).get('reset_epoch'):
            requested.set()
    monkeypatch.setattr(sessions, 'write_json', write)
    monkeypatch.setattr(registry, 'run_task', ready[3].run)
    with ThreadPoolExecutor(1) as pool:
        try:
            with insight_pipeline.serialized(ready[0].sid):
                reset = pool.submit(pipeline.run, context(ready, fresh=True))
                assert requested.wait(5)
                with pytest.raises(sessions.StoreError) as exc:
                    insights.confirm(ready[0].sid, 'v1', ['I1'])
                assert exc.value.kind == 'persona_required'
        finally:
            reset.result(timeout=10)
