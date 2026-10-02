"""Final review regressions, D-259 through D-266 and backend minors."""
import json
from types import SimpleNamespace

import numpy as np
import pytest
from pydantic import ValidationError

from app.context import store as sessions, versions
from app.evidence import assemble, candidates, novelty, pipeline, queries, tagging
from app.evidence.cache import TagCache, prompt_version
from app.evidence.package import EvidencePackage
from app.llm import registry
from app.llm.base import failure
from app.routers import evidence as api
from app.segment import pipeline as segment_pipeline
from tests.evidence.test_pipeline import setup
from tests.evidence.test_assemble import persisted
from tests.evidence.test_queries import inputs, output, runner


def test_d259_required_quality_keys(persisted):
    sid, version, _, seg, _ = persisted
    with seg._db(write=True) as db:
        db.execute('UPDATE contexts SET quality_json=? WHERE context_id=?',
                   (json.dumps(dict(cohesion=.8, boundary=.4, stability=.7, npmi=.6)), 'c1'))
    value = assemble.assemble(sid, version).model_dump(by_alias=True)
    assert set(value['personas'][0]['context_evidence'][1]['metrics']['quality']) == {'cohesion','boundary','stability','npmi'}
    del value['personas'][0]['context_evidence'][0]['metrics']['quality']['boundary']
    with pytest.raises(ValidationError):
        EvidencePackage.model_validate(value)


@pytest.mark.parametrize('initial', [None, {'status':'none'}])
def test_d260_first_segment_not_stale(setup, initial):
    sessions.update_session(setup.sid, {'evidence':initial or {}})
    segment_pipeline._session(setup.sid, 'v1', {'status':'running'}, reset=True)
    assert sessions.load_session(setup.sid).get('evidence', {}).get('status', 'none') == 'none'


def test_d261_statement_after_done_and_edit(setup):
    pipeline.run(setup.ctx)
    ki = dict(id='ki_statement', type='statement', text='예약을 원한다')
    sessions.update_session(setup.sid, {'knownInsights':[ki]})
    setup.calls.clear()
    pipeline.refresh_new(setup.sid, 'v1', 'c0', setup.ev.get_run())
    assert setup.calls and set(setup.calls) == {'evidence.tag'}
    assert not api.status(setup.sid)['contexts'][0]['knownChanged']
    setup.calls.clear()
    pipeline.refresh_new(setup.sid, 'v1', 'c0', setup.ev.get_run())
    assert not setup.calls
    ki['text'] = '예약을 원하지 않는다'
    sessions.update_session(setup.sid, {'knownInsights':[ki]})
    assert api.status(setup.sid)['contexts'][0]['knownChanged']
    pipeline.refresh_new(setup.sid, 'v1', 'c0', setup.ev.get_run())
    assert setup.calls


def test_d261_failed_judgment_stays_changed(setup, monkeypatch):
    pipeline.run(setup.ctx)
    sessions.update_session(setup.sid, {'knownInsights':[dict(id='ki_s', type='statement', text='예약')]})
    monkeypatch.setattr(registry, 'run_task', lambda t: failure('backend', 'offline'))
    pipeline.refresh_new(setup.sid, 'v1', 'c0', setup.ev.get_run())
    assert api.status(setup.sid)['contexts'][0]['knownChanged']


@pytest.mark.parametrize('vectors', [np.zeros((1,8)), np.ones((0,8)), np.full((1,8), np.nan)])
def test_d262_invalid_query_embeddings(setup, vectors):
    with pytest.raises(ValueError, match='retryable'):
        candidates.search_context('c0', [dict(text='x',dim='Sense')], docs={'d':dict(context_id='c0',band='core')},
                                  store=None, embedder=SimpleNamespace(embed=lambda *a, **k: vectors))


def test_d263_prompt_generation_pinned_then_invalidated(setup, monkeypatch):
    pipeline.run(setup.ctx)
    before = api.context(setup.sid, 'c0')['items']
    original = pipeline.prompt_version
    monkeypatch.setattr(pipeline, 'prompt_version', lambda name: 'a'*12 if name == 'tag' else original(name))
    monkeypatch.setattr(assemble, 'prompt_version', pipeline.prompt_version)
    monkeypatch.setattr(api, 'prompt_version', pipeline.prompt_version)
    assert api.context(setup.sid, 'c0')['items'] == before
    setup.calls.clear()
    pipeline.run(setup.ctx)
    assert 'evidence.tag' in setup.calls


def test_d263_segment_generation_refuses_publication(setup, monkeypatch):
    original = pipeline.novelty.judge_novelty
    def changed(*a, **kw):
        result = original(*a, **kw)
        setup.seg.set_run('changed')
        return result
    monkeypatch.setattr(pipeline.novelty, 'judge_novelty', changed)
    with pytest.raises(sessions.StoreError, match='generation'):
        pipeline.run(setup.ctx)
    assert sessions.load_session(setup.sid)['evidence']['status'] != 'done'


def test_d264_persona_violation_isolated(inputs):
    persona, contexts = inputs
    value = output(contexts)
    value['persona_query']['artifact'] *= 2
    call, _ = runner(value)
    result = queries.generate_queries('test', persona, contexts, '', run_task=call)
    assert result.failed == []
    assert len(result.persona_rows) == 3
    assert all(r['origin']=='fallback' for r in result.persona_rows)


def test_d265_deleted_ki_cache_preserved(setup):
    pipeline.run(setup.ctx)
    cache = TagCache.open(setup.sid, 'p_0123456789ab', prompt_version('tag'))
    cache.put_known({('d00','ki_deleted'):True}, 'fake')
    row = setup.ev.contexts()[0]
    setup.ev.set_context('c0','p1','done',counts={**row['counts'],'knownIds':['ki_deleted']})
    pipeline.refresh_new(setup.sid,'v1','c0',setup.ev.get_run())
    assert cache.get_known(['d00'],['ki_deleted']) == {('d00','ki_deleted'):True}


def test_d266_quote_source_and_novelty():
    docs = {'d':dict(body='unrelated body', comments=[{'text':'😀 quote here'}])}
    tags = {'d':dict(quotes=[dict(field='comment',idx=0,text='quote')])}
    item = api._view(dict(doc_id='d',novelty='high'),docs,tags)
    assert item['quoteSource'] == dict(field='comment',idx=0,text='😀 quote here')
    assert item['quoteSource']['text'][item['quote']['start']:item['quote']['end']] == 'quote'
    assert item['noveltyShown'] is True
    assert api._view(dict(doc_id='d',novelty='low'),docs,tags)['noveltyShown'] is False


def test_d266_tag_calls(setup):
    pipeline.run(setup.ctx)
    report = sessions.read_json(setup.ev.path.parent/'stage_7.json')
    assert report['tag_calls'] == setup.calls.count('evidence.tag') > 0


def test_i6_refresh_clears_all_only_novelty(setup):
    pipeline.run(setup.ctx)
    chosen = setup.ev.selected('c0','new')[0]['doc_id']
    sessions.update_session(setup.sid, {'knownInsights':[dict(id='ki_doc',type='doc',doc_id=chosen,text='예약', **{'from':'rag'})]})
    pipeline.refresh_new(setup.sid,'v1','c0',setup.ev.get_run())
    assert next(r for r in setup.ev.selected('c0','all') if r['doc_id']==chosen)['novelty'] is None


def test_i7_flag_removed_and_restart_empty(persisted):
    sid, version, base, seg, ev = persisted
    assemble.assemble(sid,version)
    assert 'undifferentiated_candidate' in seg.contexts()[0]['flags']
    ev.write_candidates('c1',[])
    assemble.assemble(sid,version)
    assert 'undifferentiated_candidate' not in seg.contexts()[0]['flags']
    assemble.append_context_flag(seg,'c1','undifferentiated_candidate')
    data = {'evidence':{'status':'done'}}
    versions._restart(data,base,7)
    assert data['evidence']['status'] == 'none'
    assert 'undifferentiated_candidate' not in seg.contexts()[0]['flags']


def test_m1_act_mismatch(persisted):
    sid, version, base, _, _ = persisted
    cache = TagCache.open(sid,'p_0123456789ab',prompt_version('tag'))
    tag = cache.get_tags(['d0'])['d0']
    tag['context_dims'] = {'activity_response':'adjust'}
    cache.put_tags({'d0':tag},'fake')
    assemble.assemble(sid,version)
    assert sessions.read_json(base/'evidence/stage_7.json')['act_mismatch'] == 1


def test_m2_counter_mean_uses_candidate_pool(persisted):
    sid, version, _, _, ev = persisted
    ev.write_candidates('c1',[dict(doc_id='d0',relevance=1,dims_hit=['Counter'],band='edge')])
    result = assemble.assemble(sid,version)
    assert result.personas[0].context_evidence[0].counter_evidence == []


def test_m3_verified_quote_after_unverified():
    item = assemble._item('d', {'d':dict(body='real quote')}, {'d':dict(quotes=[dict(field='body',text='missing'),dict(field='body',text='real')])})
    assert item['quote']['verified'] and item['quote']['text']=='real'


def test_m4_novelty_excerpts():
    captured = []
    doc = dict(doc_id='d',body='x'*10000,comments=[{'text':'y'*900}]*20,theta_json='private',_input={'big':'x'})
    novelty.judge_novelty('test',{},[doc],[doc],[],run_task=lambda t: captured.append(t) or failure('backend','test'))
    payload = json.loads(captured[0].attachments[0].body)
    for key in ('new_rows','core_reps'):
        row = payload[key][0]
        assert len(row['body']) == 1500 and len(row['comments']) == 10
        assert len(row['comments'][0]['text']) == 300
        assert 'theta_json' not in row and '_input' not in row


def test_m8_refresh_does_not_load_session(setup, monkeypatch):
    pipeline.run(setup.ctx)
    monkeypatch.setattr(pipeline,'_load',lambda *a: pytest.fail('full session reload'))
    pipeline.refresh_new(setup.sid,'v1','c0',setup.ev.get_run())


def test_m9_doc_ki_not_llm_judged(setup):
    pipeline.run(setup.ctx)
    sessions.update_session(setup.sid, {'knownInsights':[dict(id='ki_doc',type='doc',doc_id='d00',text='doc secret', **{'from':'rag'})]})
    cache = TagCache.open(setup.sid,'p_0123456789ab',prompt_version('tag'))
    calls=[]
    tagging.judge_known(setup.sid,['d00'],['ki_doc'],cache=cache,run_task=lambda t: calls.append(t) or failure('backend','test'))
    assert calls == []


def test_codex1_assembly_preserves_live_context_state(persisted, monkeypatch):
    sid, version, _, _, ev = persisted
    original = assemble.undifferentiated_candidate
    changed = False
    def interleave(*a):
        nonlocal changed
        if not changed:
            changed = True
            ev.set_context('c1','p1','done',coverage=6,counts={'new_count':99})
        return original(*a)
    monkeypatch.setattr(assemble,'undifferentiated_candidate',interleave)
    assemble.assemble(sid,version)
    row = ev.contexts()[0]
    assert row['counts']['new_count'] == 99 and row['coverage'] == 6


@pytest.mark.parametrize('first,second',[('segment','evidence'),('evidence','segment')])
def test_d263_worker_launch_conflict_atomic(data_dir, monkeypatch, first, second):
    import os
    from app.work import runner as workers
    from app.work.status import transaction
    monkeypatch.setattr(workers,'refresh',lambda db: None)
    with transaction('test') as db:
        db.execute("INSERT INTO runs (run_id,version,kind,args_json,pid,state,heartbeat_at,started_at) VALUES (?,?,?,?,?,'running',0,0)",
                   ('existing','v1',first,'{}',os.getpid()))
    monkeypatch.setattr(workers.subprocess,'Popen',lambda *a,**k: pytest.fail('conflicting process launched'))
    with pytest.raises(sessions.StoreError):
        workers.start('test','v1',second,{})


def test_i7_badge_existing_flag_readable(setup):
    assemble.append_context_flag(setup.seg,'c0','undifferentiated_candidate')
    assert api.context(setup.sid,'c0')['undifferentiated'] == []


def test_d259_persona_quality_from_sqlite(persisted):
    sid, version, _, seg, _ = persisted
    with seg._db(write=True) as db:
        columns = {r['name'] for r in db.execute('PRAGMA table_info(personas)')}
        assert 'quality_json' in columns
        db.execute('UPDATE personas SET quality_json=?', (json.dumps(dict(cohesion=.8,boundary=.6,stability_ari=.7)),))
    quality = assemble.assemble(sid,version).personas[0].persona_evidence.quality
    assert quality['cohesion'] == .8 and quality['boundary'] == .6 and quality['stability_ari'] == .7


def test_d262_persona_embedding_failure_marks_contexts_retryable(setup, monkeypatch):
    monkeypatch.setattr(pipeline.candidates,'search_persona',lambda *a,**k: (_ for _ in ()).throw(ValueError('query_embedding_failed (retryable)')))
    pipeline.run(setup.ctx)
    assert all(r['status']=='failed' and 'retryable' in r['error'] for r in setup.ev.contexts())
    assert sessions.load_session(setup.sid)['evidence']['status']=='partial'


def test_d263_generation_metadata_complete(setup):
    pipeline.run(setup.ctx)
    ref = sessions.read_json(setup.ev.path.parent/'generation.json')
    assert ref['prepKey']=='p_0123456789ab'
    assert ref['segmentRun'] == setup.seg.get_run()
    assert set(ref['prompts']) == {'tag','queries','novelty','dims'}


def test_codex1_publication_owns_session_lock(setup, monkeypatch):
    from contextlib import contextmanager
    original_lock = sessions.locked
    original_set = setup.ev.__class__.set_context
    held = 0
    @contextmanager
    def locked(sid):
        nonlocal held
        with original_lock(sid):
            held += 1
            try:
                yield
            finally:
                held -= 1
    def publish(self,cid,pid,status,**fields):
        if status == 'done' and 'coverage' in fields:
            assert held > 0, 'completion published without refresh lock'
        return original_set(self,cid,pid,status,**fields)
    monkeypatch.setattr(sessions,'locked',locked)
    monkeypatch.setattr(setup.ev.__class__,'set_context',publish)
    pipeline.run(setup.ctx)
    assert all(r['status']=='done' for r in setup.ev.contexts())


def test_d263_package_read_rejects_changed_segment(setup):
    pipeline.run(setup.ctx)
    setup.seg.set_run('new-segment')
    with pytest.raises(sessions.StoreError, match='generation'):
        api.package(setup.sid)


def test_d263_refresh_prompt_upgrade_refused(setup, monkeypatch):
    pipeline.run(setup.ctx)
    monkeypatch.setattr(pipeline.generation, 'prompt_version', lambda name:'a'*12)
    with pytest.raises(sessions.StoreError, match='프롬프트'):
        pipeline.refresh_new(setup.sid,'v1','c0',setup.ev.get_run())


def test_d261_only_new_statement_pairs_and_old_fingerprint_retained(setup, monkeypatch):
    import math
    from app.evidence.cache import known_key
    pipeline.run(setup.ctx)
    first = dict(id='ki_a',type='statement',text='first sentence')
    second = dict(id='ki_b',type='statement',text='second sentence')
    sessions.update_session(setup.sid, {'knownInsights':[first]})
    pipeline.refresh_new(setup.sid,'v1','c0',setup.ev.get_run())
    cache = TagCache.open(setup.sid,'p_0123456789ab',prompt_version('tag'))
    ids = [r['doc_id'] for r in setup.ev.candidates('c0')]
    old = cache.get_known(ids,[known_key(first)])
    captured=[]
    def call(task):
        captured.append(task)
        assert api.status(setup.sid)['contexts'][0]['knownChanged']
        return setup.backend(task)
    monkeypatch.setattr(registry,'run_task',call)
    sessions.update_session(setup.sid, {'knownInsights':[first,second]})
    pipeline.refresh_new(setup.sid,'v1','c0',setup.ev.get_run())
    assert len(captured) == math.ceil(len(ids)/8)
    assert all('second sentence' in t.instructions and 'first sentence' not in t.instructions for t in captured)
    sessions.update_session(setup.sid, {'knownInsights':[dict(first,text='edited sentence'),second]})
    pipeline.refresh_new(setup.sid,'v1','c0',setup.ev.get_run())
    assert cache.get_known(ids,[known_key(first)]) == old and old


def test_d262_missing_context_queries_retryable(setup, monkeypatch):
    original = setup.ev.__class__.queries
    def query(self, owner=None):
        return [] if owner == 'context:c0' else original(self,owner)
    monkeypatch.setattr(setup.ev.__class__,'queries',query)
    pipeline.run(setup.ctx)
    row = setup.ev.contexts()[0]
    assert row['status']=='failed' and 'retryable' in row['error']
