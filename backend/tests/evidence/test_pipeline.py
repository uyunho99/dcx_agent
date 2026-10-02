"""Offline worker lifecycle, Context isolation and generation contracts."""
import json
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from app.config import settings
from app.context import store as sessions, versions
from app.evidence import pipeline
from app.evidence.cache import TagCache, prompt_version
from app.evidence.store import EvidenceStore
from app.llm import registry
from app.llm.base import failure
from app.model.infer import prepared_root
from app.segment.store import SegmentStore
from app.vectors.embedder import FakeEmbedder
from app.vectors.store import VectorStore
from tests.fixtures.evidence_synth import fake_evidence_backend
from tests.context.test_api import create


@pytest.fixture
def setup(client, monkeypatch):
    sid = create(client)
    monkeypatch.setattr(settings, 'embed_backend', 'fake')
    monkeypatch.setattr(settings, 'embed_dim', 8)
    monkeypatch.setattr(settings, 'evidence_llm_concurrency', 1)
    sessions.update_session(sid, dict(segment={'status': 'done'}, prep=dict(status='done', derivedRef=dict(collectionId='c1', prepKey='p_0123456789ab'))))
    root = prepared_root(sid, sessions.load_session(sid))
    (root / 'docs').mkdir(parents=True)
    docs = {f'd{i:02}': dict(doc_id=f'd{i:02}', title='예약 냉방', body='잠들기 전에 예약했어요.', source='cafe', comments=[], evidence_level='edge') for i in range(36)}
    sessions.atomic_write(root / 'docs/part.jsonl', ''.join(json.dumps(d)+'\n' for d in docs.values()))
    VectorStore(root).write_shard(list(docs), FakeEmbedder().embed(list(docs)), [False]*len(docs))
    seg = SegmentStore.open(sid, 'v1')
    contexts = [dict(context_id=f'c{i}', persona_id='p1', name='예약 냉방', action='예약', keywords=['예약', '냉방'], centroid=[1.]+[0.]*7, confirmed_at='now') for i in range(3)]
    seg.write_layers(clusters=[dict(cluster_id='cl1')], personas=[dict(persona_id='p1', cluster_id='cl1', name='휴식', desire='편안함', goals=['휴식'], confirmed_at='now')], contexts=contexts,
        docs=[dict(doc_id=d, persona_id='p1', context_id=f'c{i//12}', band='edge', theta=.5, combo_rarity=.5) for i,d in enumerate(docs)])
    calls = []
    def backend(task):
        calls.append(task.task)
        batch = {a.title: docs[a.title] for a in task.attachments if a.title in docs}
        if task.task == 'evidence.novelty':
            batch = docs
        return fake_evidence_backend(contexts, batch).run(task)
    monkeypatch.setattr(registry, 'run_task', backend)
    pulses = []
    ctx = SimpleNamespace(sid=sid, version='v1', args={}, should_stop=lambda: False, heartbeat=lambda p,d: pulses.append(dict(d)))
    return SimpleNamespace(sid=sid, ctx=ctx, calls=calls, pulses=pulses, docs=docs, seg=seg, ev=EvidenceStore.open(sid,'v1'), backend=backend)


def test_runs_all_contexts(setup):
    pipeline.run(setup.ctx)
    assert {r['status'] for r in setup.ev.contexts()} == {'done'}, setup.ev.contexts()
    assert sessions.load_session(setup.sid)['evidence']['status'] == 'done'
    base = versions.version_dir(setup.sid,'v1') / 'evidence'
    assert all((base / name).exists() for name in ('package.json','stage_7.json','queries.json','checkpoint.json'))
    assert all(setup.ev.selected(f'c{i}','all') for i in range(3))
    assert setup.ev.snapshot().persona_support


def test_resume_skips_done_contexts(setup):
    setup.ctx.should_stop = lambda: any(r['status']=='done' for r in setup.ev.contexts())
    with pytest.raises(BaseException):
        pipeline.run(setup.ctx)
    completed = [r['context_id'] for r in setup.ev.contexts() if r['status']=='done']
    assert completed == ['c0']
    previous = setup.ev.selected('c0')
    old_run = setup.ev.get_run()
    setup.calls.clear()
    setup.ctx.should_stop = lambda: False
    pipeline.run(setup.ctx)
    assert setup.ev.selected('c0') == previous
    assert setup.ev.get_run() != old_run
    assert setup.calls.count('evidence.queries') == 0
    assert setup.calls.count('evidence.novelty') == 2


def test_context_failure_isolated(setup, monkeypatch):
    original = pipeline.candidates.search_context
    def search(cid, *a, **kw):
        if cid == 'c1': raise ValueError('broken context')
        return original(cid,*a,**kw)
    monkeypatch.setattr(pipeline.candidates,'search_context',search)
    pipeline.run(setup.ctx)
    rows = setup.ev.contexts()
    assert [r['status'] for r in rows] == ['done','failed','done']
    assert rows[1]['error'] == 'broken context'
    assert sessions.load_session(setup.sid)['evidence']['status'] == 'partial'
    pipeline.skip_context(setup.sid,'v1','c1',setup.ev.get_run())
    assert sessions.load_session(setup.sid)['evidence']['status'] == 'done'


@pytest.mark.parametrize('step', ['queries','tag','novelty'])
def test_all_llm_backend_failures_interrupt(setup, monkeypatch, step):
    monkeypatch.setattr(registry,'run_task',lambda t: failure('backend','offline') if t.task == 'evidence.'+step else setup.backend(t))
    with pytest.raises(BaseException): pipeline.run(setup.ctx)
    state = sessions.load_session(setup.sid)['evidence']
    assert state['status'] == 'interrupted'
    assert state['reason'] == pipeline.LLM_REASON


def test_concurrency_1_vs_4_same_package(setup, monkeypatch):
    pipeline.run(setup.ctx)
    first = [(r['context_id'],r['tab'],r['rank'],r['doc_id']) for r in setup.ev.snapshot().selected]
    cache = TagCache.open(setup.sid,'p_0123456789ab',prompt_version('tag'))
    with cache._db(write=True) as db:
        db.execute('DELETE FROM tags')
    monkeypatch.setattr(settings,'evidence_llm_concurrency',4)
    setup.ctx.args = {'fresh':True}
    threads = []
    original = TagCache.put_tags
    def put(self,*a,**kw):
        threads.append(threading.current_thread())
        return original(self,*a,**kw)
    monkeypatch.setattr(TagCache,'put_tags',put)
    pipeline.run(setup.ctx)
    assert first == [(r['context_id'],r['tab'],r['rank'],r['doc_id']) for r in setup.ev.snapshot().selected]
    assert threads and all(t is threading.main_thread() for t in threads)


def test_known_added_midrun_applies_to_pending(setup):
    def pulse(p,d):
        if any(r['status']=='done' for r in setup.ev.contexts()) and not sessions.load_session(setup.sid).get('knownInsights'):
            sessions.update_session(setup.sid, {'knownInsights':[dict(id='ki_new',type='doc',doc_id='d12',text='예약', **{'from':'rag'})]})
    setup.ctx.heartbeat = pulse
    pipeline.run(setup.ctx)
    assert setup.ev.contexts()[0]['counts']['knownChanged'] is True
    assert 'd12' not in [r['doc_id'] for r in setup.ev.selected('c1','new')]
    assert next(r for r in setup.ev.candidates('c1') if r['doc_id']=='d12')['known_excluded']=='handed'


def test_known_deleted_midrun(setup):
    sessions.update_session(setup.sid, {'knownInsights':[dict(id='ki_old',type='doc',doc_id='d00',text='예약', **{'from':'rag'})]})
    def pulse(p,d):
        if any(r['status']=='done' for r in setup.ev.contexts()) and sessions.load_session(setup.sid).get('knownInsights'):
            cache = TagCache.open(setup.sid,'p_0123456789ab',prompt_version('tag'))
            cache.put_known({('d00','ki_old'): True}, 'fake')
            sessions.update_session(setup.sid, {'knownInsights':[]})
    setup.ctx.heartbeat = pulse
    pipeline.run(setup.ctx)
    assert not any(r['known_excluded'] for r in setup.ev.candidates('c0'))
    cache = TagCache.open(setup.sid,'p_0123456789ab',prompt_version('tag'))
    assert cache.get_known(setup.docs,['ki_old']) == {('d00','ki_old'): True}


@pytest.mark.parametrize('action',['refresh_new','skip_context'])
def test_stale_run_409_on_refresh(setup, action):
    pipeline.run(setup.ctx)
    with pytest.raises(sessions.StoreError) as exc:
        getattr(pipeline,action)(setup.sid,'v1','c0','old')
    assert (exc.value.status,exc.value.kind)==(409,'stale_run')


def test_refresh_new_zero_llm(setup):
    pipeline.run(setup.ctx)
    setup.calls.clear()
    before = setup.ev.selected('c0','all')
    response = pipeline.refresh_new(setup.sid,None,'c0',setup.ev.get_run())
    assert {'context','tab','items','counter','rare','excludedKnown','queries','queryFailed','undifferentiated'} <= response.keys()
    assert {'docId','source','location','quote','text','tags','band','novelty','noveltyReason','knownMatch','rare','role'} <= response['items'][0].keys()
    assert setup.calls == []
    assert setup.ev.selected('c0','all') == before


def test_segment_rerun_marks_stale(setup, monkeypatch):
    from app.segment import pipeline as segment
    pipeline.run(setup.ctx)
    sessions.update_session(setup.sid, {'completion':{'evidenceDone':True}})
    monkeypatch.setattr(segment.inputs,'load_input',lambda *a,**kw: (_ for _ in ()).throw(ValueError('stop after reset')))
    setup.ctx.args={'fresh':True}
    with pytest.raises(ValueError): segment.run(setup.ctx)
    state = sessions.load_session(setup.sid)
    assert state['evidence']=={'status':'stale'}
    assert 'evidenceDone' not in state['completion']
    with pytest.raises(sessions.StoreError) as exc: pipeline.refresh_new(setup.sid,'v1','c0',setup.ev.get_run())
    assert exc.value.kind=='stale_run'


def test_heartbeat_per_context(setup):
    pipeline.run(setup.ctx)
    assert {p.get('context') for p in setup.pulses} >= {'c0','c1','c2'}
    assert any(p.get('step')=='tag' for p in setup.pulses)


def test_concurrency_cap_and_context_pool(setup, monkeypatch):
    monkeypatch.setattr(settings, 'evidence_llm_concurrency', 4)
    guard = threading.Lock()
    active = peak = 0
    search_threads = set()
    original_search = pipeline.candidates.search_context
    def search(*args, **kwargs):
        search_threads.add(threading.current_thread().ident)
        return original_search(*args, **kwargs)
    def call(task):
        nonlocal active, peak
        with guard:
            active += 1
            peak = max(peak, active)
        try:
            time.sleep(.01)
            return setup.backend(task)
        finally:
            with guard: active -= 1
    monkeypatch.setattr(pipeline.candidates, 'search_context', search)
    monkeypatch.setattr(registry, 'run_task', call)
    pipeline.run(setup.ctx)
    assert 1 < peak <= 4
    assert len(search_threads) > 1
    assert threading.main_thread().ident not in search_threads


def test_retry_selected_failed_context_only(setup, monkeypatch):
    original = pipeline.candidates.search_context
    def bad(cid, *a, **kw):
        if cid == 'c1': raise ValueError('once')
        return original(cid, *a, **kw)
    monkeypatch.setattr(pipeline.candidates, 'search_context', bad)
    pipeline.run(setup.ctx)
    setup.calls.clear()
    monkeypatch.setattr(pipeline.candidates, 'search_context', original)
    setup.ctx.args = {'contexts':['c1']}
    pipeline.run(setup.ctx)
    assert setup.calls == ['evidence.novelty']
    assert sessions.load_session(setup.sid)['evidence']['status'] == 'done'


def test_report_call_count_survives_refresh(setup):
    pipeline.run(setup.ctx)
    path = versions.version_dir(setup.sid, 'v1')/'evidence/stage_7.json'
    count = sessions.read_json(path)['llm_calls']
    assert count == len(setup.calls) and count > 0
    pipeline.refresh_new(setup.sid, 'v1', 'c0', setup.ev.get_run())
    assert sessions.read_json(path)['llm_calls'] == count


def test_stale_actions_after_resume(setup):
    pipeline.run(setup.ctx)
    old = setup.ev.get_run()
    pipeline.run(setup.ctx)
    for action in (pipeline.refresh_new, pipeline.skip_context):
        with pytest.raises(sessions.StoreError) as exc:
            action(setup.sid, 'v1', 'c0', old)
        assert exc.value.kind == 'stale_run'


def test_tag_failure_isolated_and_sqlite_writes_on_main_thread(setup, monkeypatch):
    # Bypass Persona retrieval so this exception belongs to a Context batch.
    monkeypatch.setattr(pipeline.candidates, 'search_persona', lambda *a, **kw: [])
    original = pipeline.tagging.tag_documents
    writers = []
    def tag(sid, ids, **kw):
        writers.append(threading.current_thread())
        if any('12' <= i[1:] < '24' for i in ids):
            raise TimeoutError('local cache timeout')
        return original(sid, ids, **kw)
    monkeypatch.setattr(pipeline.tagging, 'tag_documents', tag)
    pipeline.run(setup.ctx)
    assert [r['status'] for r in setup.ev.contexts()] == ['done', 'failed', 'done']
    assert all(t is threading.main_thread() for t in writers)


def test_worker_registered():
    from app.work.worker import KINDS
    assert 'evidence' in KINDS


def test_real_stage6_outputs_feed_pipeline(data_dir, monkeypatch):
    from tests.fixtures.evidence_synth import make_evidence_session, QueryEmbedder
    monkeypatch.setattr(settings, 'embed_backend', 'fake')
    monkeypatch.setattr(settings, 'embed_dim', 1024)
    monkeypatch.setattr(settings, 'evidence_llm_concurrency', 4)
    fixture = make_evidence_session(data_dir, clusters=3, personas=(1,1,1), contexts=(2,2,2), docs_per_context=12)
    source = pipeline._load(fixture.sid, fixture.version)
    contexts = source['seg'].contexts()
    monkeypatch.setattr(pipeline.known_store, 'get_embedder', lambda: QueryEmbedder(fixture, source['source']))
    def call(task):
        owned = [c for c in contexts if c['context_id'] + ' ·' in task.attachments[0].body] if task.task == 'evidence.queries' else contexts
        docs = {a.title: source['docs'][a.title] for a in task.attachments if a.title in source['docs']}
        if task.task == 'evidence.novelty':
            docs = {r['doc_id']: source['docs'][r['doc_id']] for r in json.loads(task.attachments[0].body)['new_rows']}
        return fake_evidence_backend(owned, docs).run(task)
    monkeypatch.setattr(registry, 'run_task', call)
    ctx = SimpleNamespace(sid=fixture.sid, version=fixture.version, args={}, should_stop=lambda: False, heartbeat=lambda *a: None)
    pipeline.run(ctx)
    assert sessions.load_session(fixture.sid)['evidence']['status'] == 'done'
    ev = EvidenceStore.open(fixture.sid, fixture.version)
    assert all(r['status']=='done' for r in ev.contexts()), ev.contexts()
    assert all(ev.selected(c['context_id'], 'all') for c in contexts)
    report = sessions.read_json(ev.path.parent/'stage_7.json')
    assert report['untagged'] == report['query_gen_fail'] == 0
    package = sessions.read_json(ev.path.parent/'package.json')
    assert len(package['personas']) == len(source['seg'].personas())


@pytest.mark.parametrize('change', ['add', 'delete'])
def test_known_changes_between_selection_and_novelty(setup, monkeypatch, change):
    item = dict(id='ki_late', type='doc', doc_id='d00', text='예약', **{'from':'rag'})
    if change == 'delete':
        sessions.update_session(setup.sid, {'knownInsights':[item]})
    original = pipeline.tabs.new_tab
    changed = False
    def select(cid, *a, **kw):
        nonlocal changed
        result = original(cid, *a, **kw)
        if cid == 'c0' and not changed:
            changed = True
            sessions.update_session(setup.sid, {'knownInsights':[item] if change == 'add' else []})
        return result
    monkeypatch.setattr(pipeline.tabs, 'new_tab', select)
    pipeline.run(setup.ctx)
    row = setup.ev.contexts()[0]
    if change == 'add':
        assert row['counts']['knownChanged'] is True
    else:
        assert not any(r['known_excluded'] for r in setup.ev.candidates('c0'))


def test_resume_records_current_concurrency(setup, monkeypatch):
    pipeline.run(setup.ctx)
    setup.calls.clear()
    monkeypatch.setattr(settings, 'evidence_llm_concurrency', 4)
    pipeline.run(setup.ctx)
    assert setup.calls == []
    package = sessions.read_json(setup.ev.path.parent/'package.json')
    assert package['params']['CONCURRENCY'] == 4
    assert setup.ev.snapshot().params['CONCURRENCY'] == 4


@pytest.mark.parametrize('survivors', [0, 1])
def test_nearly_all_untagged_contexts_fail_retryably(setup, monkeypatch, survivors):
    # Schema failures, not provider outages, must become per-Context failures.
    from app.llm.base import validate
    def backend(task):
        if task.task == 'evidence.tag':
            result = setup.backend(task)
            value = result.data.model_dump()
            value['items'] = [r for r in value['items'] if r['doc_id'] == 'd00'] if survivors else []
            return validate(task, json.dumps(value))
        return setup.backend(task)
    monkeypatch.setattr(registry, 'run_task', backend)
    pipeline.run(setup.ctx)
    assert all(r['status'] == 'failed' for r in setup.ev.contexts())
    assert all(r['error'] == '근거 원문을 태깅하지 못했습니다. 다시 시도하세요.' for r in setup.ev.contexts())
    assert all(not setup.ev.selected(f'c{i}') for i in range(3))
    monkeypatch.setattr(registry, 'run_task', setup.backend)
    pipeline.run(setup.ctx)
    assert all(r['status'] == 'done' for r in setup.ev.contexts())


def test_qa_fake_tagger_context_failure_retry_and_skip(setup, monkeypatch):
    from app.llm.fake import FakeBackend
    config = sessions.root_dir(setup.sid) / 'qa-evidence.json'
    sessions.write_json(config, dict(fail_context='c1', fail_doc_ids=[f'd{i:02}' for i in range(12, 24)]))
    monkeypatch.setattr(registry, 'run_task', FakeBackend().run)
    pipeline.run(setup.ctx)
    assert [r['status'] for r in setup.ev.contexts()] == ['done', 'failed', 'done']
    pipeline.skip_context(setup.sid, 'v1', 'c1', setup.ev.get_run())
    assert sessions.load_session(setup.sid)['evidence']['status'] == 'done'
    config.unlink()
    setup.ctx.args = {'fresh': True}
    pipeline.run(setup.ctx)
    assert all(r['status'] == 'done' for r in setup.ev.contexts())


def test_all_valid_irrelevant_judgments_are_not_tagging_failure(setup, monkeypatch):
    from app.llm.base import validate
    def irrelevant(task):
        result = setup.backend(task)
        if task.task == 'evidence.tag':
            value = result.data.model_dump()
            for row in value['items']:
                row.update(relevant=False, reason_code='no_needs')
            return validate(task, json.dumps(value))
        return result
    monkeypatch.setattr(registry, 'run_task', irrelevant)
    pipeline.run(setup.ctx)
    assert all(r['status'] == 'done' for r in setup.ev.contexts())
    assert not setup.ev.snapshot().selected
