"""Persona worker contract: real card/prescription code, local fake LLM only."""
import json
from types import SimpleNamespace

import pytest

from app.context import store as sessions
from app.context.versions import version_dir
from app.llm.base import failure
from app.persona import pipeline
from app.persona.store import PersonaStore
from app.routers.sessions import _completion
from app.segment.store import SegmentStore
from app.work import worker
from tests.fixtures.evidence_package import write_session_with_package
from tests.persona.test_cards import Runner


@pytest.fixture
def setup(data_dir, monkeypatch):
    synth = write_session_with_package(data_dir)
    root = version_dir(synth.sid, synth.version)
    # constraint_check carries only a prescription, so bind the fake's verdict
    # to the preceding Persona instead of its default first-Persona response.
    current_persona = None
    def mutate(task, output):
        nonlocal current_persona
        if task.task == 'persona.prescribe':
            current_persona = json.loads(task.attachments[0].body)['card_summary']['persona_id']
        if task.task == 'persona.constraint_check' and current_persona != 'CL0-P0':
            for row in output['constraints']:
                row.update(verdict='ok', reason='제약을 지킴')
    runner = Runner(sessions.read_json(root / 'evidence/package.json'), mutate=mutate)
    monkeypatch.setattr(pipeline.registry, 'run_task', runner)
    ctx = SimpleNamespace(sid=synth.sid, version=synth.version, args={}, run_id='worker-1',
                          should_stop=lambda: False, heartbeat=lambda *a: None)
    return ctx, root, runner


def state(ctx, root):
    return sessions.read_json(root / 'session.json')['persona']


def test_all_generated_and_registered(setup):
    ctx, root, runner = setup
    pipeline.run(ctx)
    store = PersonaStore.open(ctx.sid, ctx.version)
    assert all(store.read(name) for name in ('cards', 'map', 'tree', 'stage_8'))
    rows = store.read('cards')['personas']
    assert len(rows) == 4 and all(row['status'] == 'done' for row in rows.values())
    assert all({'card', 'grades', 'trace', 'prescription', 'constraint', 'scope'} <= row.keys() for row in rows.values())
    assert state(ctx, root)['status'] == 'done'
    assert state(ctx, root)['progress'] == 1
    assert state(ctx, root)['savedAt']
    assert 'persona' in worker.KINDS
    assert _completion(ctx.sid, sessions.read_json(root / 'session.json'), ctx.version)['personaDone']


def test_resume_skips_done_personas(setup):
    ctx, root, runner = setup
    def stop_after_one():
        checkpoint = sessions.read_json(root / 'persona/checkpoint.json') or {}
        return len(checkpoint.get('done', [])) == 1
    ctx.should_stop = stop_after_one
    pipeline.run(ctx)
    assert state(ctx, root)['status'] == 'interrupted'
    first = PersonaStore.open(ctx.sid, ctx.version).read('cards')['personas']['CL0-P0']
    before = len(runner.calls)
    old_run = state(ctx, root)['run']
    ctx.should_stop = lambda: False
    pipeline.run(ctx)
    assert state(ctx, root)['status'] == 'done'
    assert state(ctx, root)['run'] != old_run
    with pytest.raises(sessions.StoreError) as error:
        pipeline.assert_run(ctx.sid, ctx.version, old_run)
    assert error.value.kind == 'stale_run'
    assert PersonaStore.open(ctx.sid, ctx.version).read('cards')['personas']['CL0-P0'] == first
    assert all(json.loads(t.attachments[0].body)['persona_id'] != 'CL0-P0'
               for t in runner.calls[before:] if t.task == 'persona.card')


@pytest.mark.parametrize('failed_task', ['persona.card', 'persona.prescribe', 'persona.scope'])
def test_one_persona_failure_isolated(setup, monkeypatch, failed_task):
    ctx, root, runner = setup
    failed = False
    def fail_one(task):
        nonlocal failed
        if task.task == failed_task and not failed:
            failed = True
            return failure('backend', 'unavailable')
        return runner(task)
    monkeypatch.setattr(pipeline.registry, 'run_task', fail_one)
    pipeline.run(ctx)
    store = PersonaStore.open(ctx.sid, ctx.version)
    rows = store.read('cards')['personas']
    assert rows['CL0-P0']['status'] == 'failed'
    assert rows['CL0-P0']['error'] == '이 페르소나 카드를 만들지 못했습니다.'
    assert all(rows[f'CL0-P{i}']['status'] == 'done' for i in range(1, 4))
    before = len(runner.calls)
    ctx.args = {'personas': ['CL0-P0'], 'run': state(ctx, root)['run']}
    pipeline.run(ctx)
    assert store.read('cards')['personas']['CL0-P0']['status'] == 'done'
    assert [json.loads(t.attachments[0].body)['persona_id'] for t in runner.calls[before:]
            if t.task == 'persona.card'] == ['CL0-P0']


@pytest.mark.parametrize('kind', ['backend', 'timeout', 'exception'])
def test_all_backend_failures_interrupt(setup, monkeypatch, kind):
    ctx, root, _ = setup
    def unavailable(task):
        if kind == 'exception':
            raise TimeoutError()
        return failure(kind, 'unavailable')
    monkeypatch.setattr(pipeline.registry, 'run_task', unavailable)
    with pytest.raises(BaseException) as exc:
        pipeline.run(ctx)
    assert not isinstance(exc.value, Exception)
    assert state(ctx, root)['status'] == 'interrupted'
    assert state(ctx, root)['reason'] == 'LLM이 연결되지 않았거나 한도를 넘었습니다. 연결을 확인한 뒤 이어서 진행하세요.'
    assert not sessions.read_json(root / 'persona/stage_8.json')


@pytest.mark.parametrize('change', ['package_run', 'name', 'desire', 'goals', 'action'])
def test_package_changed_marks_stale(setup, change):
    ctx, root, runner = setup
    pipeline.run(ctx)
    before = len(runner.calls)
    if change == 'package_run':
        sessions.update_session(ctx.sid, {'evidence': {'run': 'new-evidence'}})
    else:
        segment = SegmentStore.open(ctx.sid, ctx.version)
        segment.confirm('contexts' if change == 'action' else 'personas',
                        'CL0-P0-C0' if change == 'action' else 'CL0-P0',
                        {change: ['new goal'] if change == 'goals' else 'changed'})
    pipeline.run(ctx)
    data = sessions.read_json(root / 'session.json')
    assert data['persona']['status'] == 'stale' and 'stage8' in data['stale']
    assert not _completion(ctx.sid, data, ctx.version)['personaDone']
    assert len(runner.calls) == before


def test_stale_run_409(setup):
    ctx, root, runner = setup
    pipeline.run(ctx)
    previous = (root / 'persona/cards.json').read_bytes()
    ctx.args = {'personas': ['CL0-P0'], 'run': 'obsolete'}
    with pytest.raises(sessions.StoreError) as exc:
        pipeline.run(ctx)
    assert (exc.value.status, exc.value.kind) == (409, 'stale_run')
    assert (root / 'persona/cards.json').read_bytes() == previous
    pipeline.assert_run(ctx.sid, ctx.version, state(ctx, root)['run'])


def test_stage8_report_fields(setup):
    ctx, root, runner = setup
    pipeline.run(ctx)
    report = sessions.read_json(root / 'persona/stage_8.json')
    assert {'cards', 'failed', 'grades', 'null_attributes', 'constraint_violations',
            'represcribed', 'blocked', 'future', 'zones', 'stars', 'insights',
            'above_mean', 'concepts', 'chat_revisions', 'llm_calls', 'params', 'provisional', 'run', 'at'} <= report.keys()
    assert report['cards'] == 4 and report['failed'] == 0
    assert sum(report['zones'].values()) == 11 and report['stars'] == 2
    assert report['blocked'] == report['represcribed'] == 1
    assert set(report['grades']) == {'observed', 'inferred', 'speculated'}
    assert report['null_attributes'] > 0
    assert sum(report['llm_calls'].values()) == len(runner.calls)
    assert report['params']['TRACE_MIN'] == .5


def test_source_changes_during_call_do_not_publish_done(setup, monkeypatch):
    ctx, root, runner = setup
    def change_source(task):
        result = runner(task)
        package = sessions.read_json(root / 'evidence/package.json')
        package['params']['CONCURRENCY'] = 99  # changed producer package
        sessions.write_json(root / 'evidence/package.json', package)
        return result
    monkeypatch.setattr(pipeline.registry, 'run_task', change_source)
    pipeline.run(ctx)
    assert state(ctx, root)['status'] == 'stale'
    assert not PersonaStore.open(ctx.sid, ctx.version).read('stage_8')


def test_schema_failures_are_isolated_not_backend_interruption(setup, monkeypatch):
    ctx, root, _ = setup
    monkeypatch.setattr(pipeline.registry, 'run_task', lambda task: failure('schema', 'bad shape'))
    pipeline.run(ctx)
    report = PersonaStore.open(ctx.sid, ctx.version).read('stage_8')
    assert state(ctx, root)['status'] == 'done'
    assert report['failed'] == 4 and report['cards'] == 0


def test_fresh_rebuilds_changed_package_and_resets_insights(setup):
    ctx, root, runner = setup
    pipeline.run(ctx)
    store = PersonaStore.open(ctx.sid, ctx.version)
    store.new_revision('insights', [{'id': 'old'}], by='generate', message=None)
    sessions.update_session(ctx.sid, {'evidence': {'run': 'updated-package'}})
    before = len(runner.calls)
    ctx.args = {'fresh': True}
    pipeline.run(ctx)
    assert state(ctx, root)['status'] == 'done'
    assert store.read('cards')['package_run'] == 'updated-package'
    assert len(runner.calls) > before and store.read('insights') is None


def test_report_counts_existing_downstream_artifacts(setup):
    ctx, root, _ = setup
    pipeline.run(ctx)
    store = PersonaStore.open(ctx.sid, ctx.version)
    store.new_revision('insights', [{'id': 'I1', 'odi': .5, 'default_target': False},
                                   {'id': 'I2', 'odi': 1.5, 'default_target': True}], by='generate', message=None)
    store.new_revision('concepts', [{'id': 'C1'}], by='chat', message='edit')
    pipeline.run(ctx)
    report = store.read('stage_8')
    assert (report['insights'], report['above_mean'], report['concepts'], report['chat_revisions']) == (2, 1, 1, 1)


def test_selected_personas_do_not_complete_unprocessed_units(setup):
    ctx, root, runner = setup
    ctx.args = {'personas': ['CL0-P0']}
    pipeline.run(ctx)
    data = sessions.read_json(root / 'session.json')
    assert not _completion(ctx.sid, data, ctx.version)['personaDone']
    assert data['persona']['progress'] == .25
    ctx.args = {}
    pipeline.run(ctx)
    assert state(ctx, root)['status'] == 'done'
    assert len([t for t in runner.calls if t.task == 'persona.card']) == 4
