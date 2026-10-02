"""Round-two regressions: durable refresh, generation scope and recovery."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

import pytest

from app.config import settings
from app.context import store as sessions
from app.evidence import generation, pipeline
from app.evidence.cache import known_key
from app.llm import registry
from app.routers import evidence as api
from tests.evidence.test_pipeline import setup


def test_refresh_publishes_disk_package_without_get(setup):
    pipeline.run(setup.ctx)
    chosen = setup.ev.selected('c0', 'new')[0]['doc_id']
    sessions.update_session(setup.sid, {'knownInsights': [dict(id='ki_doc', type='doc', doc_id=chosen, text='예약', **{'from': 'rag'})]})
    assert chosen in {r['doc_id'] for r in setup.ev.selected('c0', 'all')}
    pipeline.refresh_new(setup.sid, 'v1', 'c0', setup.ev.get_run())
    assert chosen not in {r['doc_id'] for r in setup.ev.selected('c0', 'new')}
    with (setup.ev.path.parent / 'package.json').open() as stream:
        package = json.load(stream)
    context = next(c for p in package['personas'] for c in p['context_evidence'] if c['context_id'] == 'c0')
    item = next(i for i in context['evidence'] if i['doc_id'] == chosen)
    assert item['tab'] == ['all']
    assert item['novelty'] is None
    assert not (setup.ev.path.parent / 'package_dirty.json').exists()


@pytest.mark.parametrize('legacy', [False, True])
def test_resume_preserves_completed_contexts_after_monitor_changes(setup, monkeypatch, legacy):
    pipeline.run(setup.ctx)
    before = setup.ev.selected('c0')
    if legacy:
        (setup.ev.path.parent / 'generation.json').unlink()
    data = sessions.load_session(setup.sid)
    sessions.update_session(setup.sid, {'training': {**data.get('training', {}), 'monitor': {'progress': 42}},
                                       'prep': {**data['prep'], 'displayNote': 'unrelated'}})
    setup.calls.clear()
    pipeline.run(setup.ctx)
    assert setup.ev.selected('c0') == before
    assert setup.calls == []


def test_generation_input_references_still_invalidate(setup):
    data = sessions.load_session(setup.sid)
    original = generation.capture(setup.sid, 'v1', data)
    for key in ('exportRef', 'modelId'):
        changed = generation.capture(setup.sid, 'v1', {**data, 'training': {key: 'changed'}})
        assert not generation.equivalent(original, changed)


def test_stale_publication_interrupts_in_korean(setup, monkeypatch):
    original = pipeline.novelty.judge_novelty
    def change(*args, **kwargs):
        result = original(*args, **kwargs)
        setup.seg.set_run('changed')
        return result
    monkeypatch.setattr(pipeline.novelty, 'judge_novelty', change)
    with pytest.raises(sessions.StoreError):
        pipeline.run(setup.ctx)
    state = sessions.load_session(setup.sid)['evidence']
    assert state['status'] == 'interrupted'
    assert '다시' in state['reason']
    assert not (setup.ev.path.parent / 'package.json').exists()


def test_running_package_get_never_assembles(setup, monkeypatch):
    pipeline.run(setup.ctx)
    root = setup.ev.path.parent
    before = (root / 'package.json').read_bytes()
    sessions.write_json(root / 'package_dirty.json', {'run': setup.ev.get_run()})
    sessions.update_session(setup.sid, {'evidence': {'status': 'running', 'run': setup.ev.get_run()}})
    monkeypatch.setattr(pipeline, '_assemble', lambda *a: pytest.fail('GET must not publish'))
    with pytest.raises(sessions.StoreError) as exc:
        api.package(setup.sid)
    assert exc.value.kind == 'not_ready'
    assert (root / 'package.json').read_bytes() == before


def test_prompt_upgrade_has_actionable_korean_recovery(setup, monkeypatch):
    pipeline.run(setup.ctx)
    monkeypatch.setattr(generation, 'prompt_version', lambda name: 'changed')
    with pytest.raises(sessions.StoreError) as exc:
        pipeline.refresh_new(setup.sid, 'v1', 'c0', setup.ev.get_run())
    assert '이어서 진행' in str(exc.value)


def test_refresh_readonly_during_judgment_writes_nothing(setup, monkeypatch):
    pipeline.run(setup.ctx)
    ki = dict(id='ki_new', type='statement', text='new statement')
    sessions.update_session(setup.sid, {'knownInsights': [ki]})
    before = setup.ev.snapshot()
    package = (setup.ev.path.parent / 'package.json').read_bytes()
    original = sessions.assert_writable
    readonly = False
    def check(*args, **kwargs):
        if readonly:
            raise sessions.StoreError('읽기 전용', 409, 'readonly')
        return original(*args, **kwargs)
    def call(task):
        nonlocal readonly
        readonly = True
        return setup.backend(task)
    monkeypatch.setattr(sessions, 'assert_writable', check)
    monkeypatch.setattr(registry, 'run_task', call)
    with pytest.raises(sessions.StoreError):
        pipeline.refresh_new(setup.sid, 'v1', 'c0', setup.ev.get_run())
    assert setup.ev.snapshot() == before
    assert (setup.ev.path.parent / 'package.json').read_bytes() == package
    assert not (setup.ev.path.parent / 'package_dirty.json').exists()
    cache = pipeline._load(setup.sid, 'v1')['cache']
    assert cache.get_known(list(setup.docs), [known_key(ki)]) == {}


def test_refresh_batches_concurrent_and_overlapping_refresh_deduplicated(setup, monkeypatch):
    pipeline.run(setup.ctx)
    sessions.update_session(setup.sid, {'knownInsights': [dict(id='ki_new', type='statement', text='new statement')]})
    monkeypatch.setattr(settings, 'evidence_llm_concurrency', 2)
    barrier, lock = Barrier(2), Lock()
    calls = 0
    def call(task):
        nonlocal calls
        with lock:
            calls += 1
        barrier.wait(timeout=5)
        return setup.backend(task)
    monkeypatch.setattr(registry, 'run_task', call)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(pipeline.refresh_new, setup.sid, 'v1', 'c0', setup.ev.get_run()) for _ in range(2)]
        for future in futures:
            future.result(timeout=15)
    assert calls == 2  # twelve candidates / eight per batch, judged only once


def test_paused_worker_conflict_explains_cancel(data_dir, monkeypatch):
    import os
    from app.work import runner
    from app.work.status import transaction
    monkeypatch.setattr(runner, 'refresh', lambda db: None)
    with transaction('test') as db:
        db.execute("INSERT INTO runs (run_id,version,kind,args_json,pid,state,heartbeat_at,started_at) VALUES (?,?,?,?,?,'paused',0,0)",
                   ('existing', 'v1', 'evidence', '{}', os.getpid()))
    with pytest.raises(sessions.StoreError) as exc:
        runner.start('test', 'v1', 'segment', {})
    assert '취소' in str(exc.value) and '일시 정지' in str(exc.value)


def test_worker_status_keeps_generation_mismatch_interrupted(setup, monkeypatch):
    import os
    import time
    from app.work import worker
    from app.work.status import transaction
    original = pipeline.novelty.judge_novelty
    def change(*args, **kwargs):
        result = original(*args, **kwargs)
        setup.seg.set_run('changed')
        return result
    monkeypatch.setattr(pipeline.novelty, 'judge_novelty', change)
    with transaction(setup.sid) as db:
        db.execute("INSERT INTO runs (run_id,version,kind,args_json,pid,state,heartbeat_at,started_at) VALUES (?,?,?,?,?,'running',?,?)",
                   ('worker', 'v1', 'evidence', '{}', os.getpid(), time.time(), time.time()))
    worker.execute(worker.Context(setup.sid, 'v1', 'evidence', {}, 'worker'))
    result = api.status(setup.sid)
    assert result['status'] == 'interrupted'
    assert '다시' in result['reason']


def test_refresh_assembly_owns_lock_and_history_reads_need_no_writes(setup, monkeypatch):
    from contextlib import contextmanager
    pipeline.run(setup.ctx)
    original_lock, original_assemble = sessions.locked, pipeline._assemble
    held, assembled = False, False
    @contextmanager
    def locked(sid):
        nonlocal held
        with original_lock(sid):
            held = True
            try:
                yield
            finally:
                held = False
    def assemble(*args):
        nonlocal assembled
        assert held
        sessions.assert_writable(*args)
        assembled = True
        return original_assemble(*args)
    monkeypatch.setattr(sessions, 'locked', locked)
    monkeypatch.setattr(pipeline, '_assemble', assemble)
    pipeline.refresh_new(setup.sid, 'v1', 'c0', setup.ev.get_run())
    assert assembled
    meta_path = sessions.root_dir(setup.sid) / 'meta.json'
    meta = sessions.read_json(meta_path)
    meta['versions'][0]['readonly'] = True
    sessions.write_json(meta_path, meta)
    monkeypatch.setattr(pipeline, '_assemble', lambda *a: pytest.fail('history GET wrote package'))
    assert api.package(setup.sid, 'v1') == sessions.read_json(setup.ev.path.parent / 'package.json')
    before = {p.name: p.read_bytes() for p in setup.ev.path.parent.iterdir() if p.is_file()}
    with pytest.raises(sessions.StoreError):
        pipeline.refresh_new(setup.sid, 'v1', 'c0', setup.ev.get_run())
    assert before == {p.name: p.read_bytes() for p in setup.ev.path.parent.iterdir() if p.is_file()}
