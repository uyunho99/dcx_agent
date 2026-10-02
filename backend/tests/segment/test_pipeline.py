import json
import re
from collections import Counter
from uuid import UUID

import pytest

from app.config import settings
from app.context import store as sessions
from app.context.versions import version_dir, create_version
from app.llm import registry
from app.segment import pipeline, params
from app.segment.store import SegmentStore
from tests.fixtures.segment_synth import make_segment_session, fake_dims_backend


class Context:
    def __init__(self, sid, version='v1', args=None, stop_after=None):
        self.sid, self.version, self.args = sid, version, args or {}
        self.stop_after = stop_after
        self.events = []
        self.stopped = False

    def heartbeat(self, progress, detail):
        self.events.append((progress, detail))
        if detail.get('completed') == self.stop_after and self.stop_after:
            self.stopped = True

    def should_stop(self):
        return self.stopped


@pytest.fixture
def setup(data_dir, monkeypatch):
    monkeypatch.setattr(settings, 'embed_backend', 'fake')
    monkeypatch.setattr(settings, 'llm_backend', 'fake')
    calls = []
    class Backend:
        def run(self, task):
            calls.append((task.task, [a.model_dump() for a in task.attachments]))
            return fake_dims_backend([a.title for a in task.attachments]).run(task)
    monkeypatch.setattr(registry, 'get_backend', lambda name: Backend())
    def build(**kwargs):
        fixture = make_segment_session(data_dir, **kwargs)
        return fixture, calls
    return build


def report(sid, version='v1'):
    return sessions.read_json(version_dir(sid, version) / 'segment/stage_6.json')


def confirm_all(sid, version='v1'):
    store = SegmentStore.open(sid, version)
    for table, key, values in [('clusters', 'cluster_id', {'name': 'confirmed'}),
            ('personas', 'persona_id', {'name': 'confirmed', 'desire': 'desire', 'goals': ['goal']}),
            ('contexts', 'context_id', {'name': 'confirmed', 'action': 'action'})]:
        for row in getattr(store, table)():
            store.confirm(table, row[key], values)
    assert pipeline.mark_done_if_complete(sid, version)


def test_end_to_end_synth(setup):
    fixture, calls = setup(docs_per_context=12)
    import os
    import time
    from app.work.worker import Context as WorkerContext, execute
    from app.work.status import transaction
    with transaction(fixture.sid) as db:
        db.execute('INSERT INTO runs(run_id,version,kind,args_json,pid,state,heartbeat_at,started_at) VALUES (?,?,?,?,?,?,?,?)',
            ('worker', 'v1', 'segment', '{}', os.getpid(), 'running', time.time(), time.time()))
    execute(WorkerContext(fixture.sid, 'v1', 'segment', {}, 'worker'))
    with transaction(fixture.sid) as db:
        assert db.execute("SELECT state FROM runs WHERE run_id='worker'").fetchone()[0] == 'done'
    store = SegmentStore.open(fixture.sid, 'v1')
    rows = store.docs(limit=10000)
    assert len(rows) == fixture.expected['documents'] - 3
    assert len({r['doc_id'] for r in rows}) == len(rows)
    for row in rows:
        for key, pattern in [('cluster_id', r'CL\d+'), ('persona_id', r'CL\d+-P\d+'), ('context_id', r'CL\d+-P\d+-C\d+')]:
            assert re.fullmatch(pattern, row[key])
        assert row['pred_entropy'] == 0 and row['sentiment'] is not None
        assert row['theta'] == max(row['theta_json'])
    data = report(fixture.sid)
    assert {'input', 'L1', 'clusters', 'personas', 'contexts', 'bands', 'dims', 'llm_calls', 'params', 'at', 'run'} <= data.keys()
    assert data['params'] == json.loads(json.dumps({k: v for k, v in vars(params).items() if k.isupper()}))
    assert data['L1']['k'] == 5
    assert all(row['boundary'] is not None for row in data['clusters'])
    assert sum(data['bands'].values()) == pytest.approx(1)
    assert data['llm_calls'] == dict(Counter(name.split('.')[1] for name, _ in calls))
    state = sessions.load_session(fixture.sid)
    assert UUID(data['run']) and data['run'] == store.get_run() == state['segment']['run']
    assert state['segment']['status'] == 'review'
    assert not state.get('completion', {}).get('segmentDone')
    assert all(p['flags'] is not None for p in store.personas())


def test_resume_skips_done_steps(setup, monkeypatch):
    fixture, calls = setup(docs_per_context=4)
    ctx = Context(fixture.sid, stop_after='L2')
    pipeline.run(ctx)
    checkpoint = sessions.read_json(version_dir(fixture.sid, 'v1') / 'segment/checkpoint.json')
    assert checkpoint['done'] == ['load', 'L1', 'L2']
    old_run = SegmentStore.open(fixture.sid, 'v1').get_run()
    monkeypatch.setattr(pipeline.l1, 'cluster', lambda *a, **kw: pytest.fail('L1 recalculated'))
    # Quality has its own L1 resampling; replace only that diagnostic.
    monkeypatch.setattr(pipeline.quality, 'resample_ari', lambda *a, **kw: 1.)
    pipeline.run(Context(fixture.sid, args={'resume': True}, stop_after='drafts'))
    before = list(calls)
    pipeline.run(Context(fixture.sid, args={'resume': True}))
    assert calls == before
    assert report(fixture.sid)['run'] != old_run


def test_heartbeat_each_persona(setup):
    fixture, _ = setup(docs_per_context=4)
    ctx = Context(fixture.sid)
    pipeline.run(ctx)
    ids = {p['persona_id'] for p in SegmentStore.open(fixture.sid, 'v1').personas()}
    for step in ('L3', 'drafts'):
        assert ids <= {d.get('persona') for _, d in ctx.events if d.get('step') == step}


def test_rerun_with_k_resets_confirmations(setup):
    fixture, _ = setup(docs_per_context=12)
    pipeline.run(Context(fixture.sid))
    confirm_all(fixture.sid)
    previous = report(fixture.sid)['run']
    pipeline.run(Context(fixture.sid, args={'k': 3}))
    store = SegmentStore.open(fixture.sid, 'v1')
    assert len(store.clusters()) == 3
    assert all(not r['confirmed_at'] for layer in ('clusters', 'personas', 'contexts') for r in getattr(store, layer)())
    assert report(fixture.sid)['run'] != previous
    assert not sessions.load_session(fixture.sid)['completion'].get('segmentDone')


def test_few_docs_warning(setup):
    fixture, _ = setup(clusters=5, personas=(1,)*5, contexts=(1,)*5, docs_per_context=43)
    pipeline.run(Context(fixture.sid))
    result = report(fixture.sid)
    assert result['L1']['k'] == 3
    assert result['warnings'][0]['key'] == 'few_docs'
    assert result['warnings'][0]['message'] == '문서가 적어(212건) 군집이 불안정할 수 있습니다.'


def test_skewed_cluster_completes(setup):
    fixture, _ = setup(clusters=3, personas=(1,1,1), contexts=(18,1,1), docs_per_context=16)
    pipeline.run(Context(fixture.sid, args={'k': 3}))
    data = report(fixture.sid)
    counts = [r['docs'] for r in data['clusters']]
    assert max(counts) / sum(counts) == pytest.approx(.9, abs=.01)
    assert min(counts) > 0
    assert sum(c['docs'] for c in data['contexts']) == sum(counts)
    assert all(c['boundary'] is not None for c in data['clusters'])


def test_llmcache_reused_across_versions(setup):
    fixture, calls = setup(docs_per_context=4)
    pipeline.run(Context(fixture.sid))
    confirm_all(fixture.sid)
    create_version(fixture.sid, 'v1', 'stage6', '')
    calls.clear()
    pipeline.run(Context(fixture.sid, 'v2'))
    assert not [c for c in calls if c[0] == 'segment.dims']


def test_clear_stale_on_done(setup):
    fixture, _ = setup(docs_per_context=4)
    pipeline.run(Context(fixture.sid))
    path = version_dir(fixture.sid, 'v1') / 'session.json'
    state = sessions.read_json(path)
    state['stale'] = {'stage6': 'old', 'stage7': 'old', 'stage8': 'old'}
    sessions.write_json(path, state)
    assert not pipeline.mark_done_if_complete(fixture.sid, 'v1')
    confirm_all(fixture.sid)
    state = sessions.read_json(path)
    assert state['segment']['status'] == 'done'
    assert state['completion']['segmentDone'] is True
    assert state['stale'] == {'stage7': 'old', 'stage8': 'old'}


def test_persona_flags_migrate_existing_db(tmp_path):
    import sqlite3
    directory = tmp_path / 'segment'
    directory.mkdir()
    with sqlite3.connect(directory / 'segment.sqlite') as db:
        db.execute('CREATE TABLE personas (persona_id TEXT PRIMARY KEY, cluster_id TEXT)')
        db.execute("INSERT INTO personas VALUES ('CL0-P0', 'CL0')")
    store = SegmentStore(tmp_path)
    assert store.personas()[0]['flags'] == []


def test_resume_mid_drafts_and_dims_never_repeats_calls(setup, monkeypatch):
    fixture, calls = setup(docs_per_context=4)
    ctx = Context(fixture.sid)
    original = ctx.heartbeat
    def stop_mid_drafts(progress, detail):
        original(progress, detail)
        if detail['step'] == 'drafts' and len([c for c in calls if c[0] == 'segment.persona_draft']) >= 1:
            ctx.stopped = True
    ctx.heartbeat = stop_mid_drafts
    pipeline.run(ctx)
    before = list(calls)
    assert any(c[0] == 'segment.persona_draft' for c in before)
    pipeline.run(Context(fixture.sid, args={'resume': True}))
    fingerprints = [json.dumps(call, sort_keys=True) for call in calls]
    assert len(fingerprints) == len(set(fingerprints))
    assert report(fixture.sid)['dims']['extracted'] > 0
    # All fake desires are equal; cross-cluster similarity must survive replay.
    assert any(p['similar'] for p in SegmentStore.open(fixture.sid, 'v1').personas())


def test_computation_does_not_hold_session_lock(setup, monkeypatch):
    from contextlib import contextmanager
    fixture, _ = setup(docs_per_context=4)
    original_lock = sessions.locked
    held = []
    @contextmanager
    def lock(sid):
        with original_lock(sid):
            held.append(True)
            try:
                yield
            finally:
                held.pop()
    monkeypatch.setattr(sessions, 'locked', lock)
    for module, name in [(pipeline.inputs, 'load_input'), (pipeline.l1, 'suggest_k'),
                         (pipeline.l2, 'personas'), (pipeline.l3, 'contexts'), (registry, 'run_task')]:
        original = getattr(module, name)
        def checked(*args, _original=original, **kwargs):
            assert not held
            return _original(*args, **kwargs)
        monkeypatch.setattr(module, name, checked)
    pipeline.run(Context(fixture.sid))


def test_counter_flags_and_persona_draft_failure_persist(setup, monkeypatch):
    fixture, _ = setup(docs_per_context=4)
    original = pipeline.l3.contexts
    def contexts(ids, tokens, vectors, sentiment_by_id=None):
        assert set(sentiment_by_id) == set(ids)
        result = original(ids, tokens, vectors, sentiment_by_id)
        result.flags.append('counter_context')
        result.context_flags[next(iter(result.centroids))] = ['counter_context']
        return result
    monkeypatch.setattr(pipeline.l3, 'contexts', contexts)
    original_call = registry.run_task
    def call(task):
        from app.llm.base import failure
        return failure('backend', 'offline failure') if task.task == 'segment.persona_draft' else original_call(task)
    monkeypatch.setattr(registry, 'run_task', call)
    pipeline.run(Context(fixture.sid))
    store = SegmentStore.open(fixture.sid, 'v1')
    assert all('draft_failed' in p['flags'] for p in store.personas())
    assert any('counter_context' in c['flags'] for c in store.contexts())


def test_resume_mid_dims_reuses_completed_batches(setup):
    fixture, calls = setup(docs_per_context=4)
    ctx = Context(fixture.sid)
    original = ctx.heartbeat
    def stop_after_batch(progress, detail):
        original(progress, detail)
        if detail['step'] == 'dims' and any(c[0] == 'segment.dims' for c in calls):
            ctx.stopped = True
    ctx.heartbeat = stop_after_batch
    pipeline.run(ctx)
    assert len(calls) == 1
    first_ids = {a['title'] for a in calls[0][1]}
    pipeline.run(Context(fixture.sid, args={'resume': True}))
    later_ids = {a['title'] for name, attachments in calls[1:] if name == 'segment.dims' for a in attachments}
    assert not first_ids & later_ids
    assert report(fixture.sid)['dims']['extracted'] > len(first_ids)
