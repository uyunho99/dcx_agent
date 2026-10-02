import pytest
from app.context import store as sessions, versions
from app.evidence.cache import TagCache, prompt_version
from app.evidence.store import EvidenceStore
from app.evidence.tagging import tag_documents
from app.routers.sessions import _completion
from app.segment.store import SegmentStore
from test_api import create


def seed(client):
    sid = create(client)
    sessions.update_session(sid, {'segment':{'status':'done'},'evidence':{'status':'done'},'completion':{'segmentDone':True,'evidenceDone':True}})
    seg = SegmentStore.open(sid,'v1')
    seg.write_layers(contexts=[dict(context_id='c1',persona_id='p1',name='확정',confirmed_at='now')])
    ev = EvidenceStore.open(sid,'v1'); ev.reset('r1',{})
    ev.set_context('c1','p1','done')
    ev.write_selected('c1','all',[dict(doc_id='d1',rank=1,role='support')])
    sessions.write_json(versions.version_dir(sid,'v1')/'evidence/stage_7.json',{'llm_calls':3,'coverage':{'c1':4},'params':{}})
    return sid


def test_restart_from7_keeps_segment_confirmations(client):
    sid=seed(client)
    versions.create_version(sid,'v1','stage7','')
    assert SegmentStore.open(sid,'v2').contexts()[0]['confirmed_at']=='now'
    assert not (versions.version_dir(sid,'v2')/'evidence').exists()
    assert 'evidenceDone' not in sessions.load_session(sid)['completion']


def test_restart_from7_reuses_tag_cache(client):
    sid=seed(client)
    cache=TagCache.open(sid,'p_0123456789ab',prompt_version('tag'))
    cache.put_tags({'d1':{'relevant':True}},'fake')
    versions.create_version(sid,'v1','stage7','')
    result=tag_documents(sid,['d1'],docs={},dims_by_id={},known_items=[],cache=TagCache.open(sid,'p_0123456789ab',prompt_version('tag')),run_task=lambda t: pytest.fail('cache miss'),concurrency=4)
    assert result.calls==0 and result.cache_hits==1


def test_restart_from6_deletes_evidence(client):
    sid=seed(client)
    versions.create_version(sid,'v1','stage6','')
    assert not (versions.version_dir(sid,'v2')/'evidence').exists()
    assert not (versions.version_dir(sid,'v2')/'segment').exists()
    assert 'evidenceDone' not in sessions.load_session(sid)['completion']


@pytest.mark.parametrize('status',['none','running','partial','failed','interrupted','stale','done'])
@pytest.mark.parametrize('stale',[{}, {'stage7':{}}])
def test_completion_evidence_done_rules(client,status,stale):
    sid=create(client)
    assert _completion(sid,{'evidence':{'status':status},'stale':stale})['evidenceDone'] == (status=='done' and not stale)


def test_compare_stage7_summary(client):
    sid=seed(client)
    versions.create_version(sid,'v1','stage7','')
    diff=versions.compare(sid,'v1','v2','stage7')
    assert diff==dict(same=False,before=dict(report={'llm_calls':3,'coverage':{'c1':4}},contexts={'c1':{'selectedAll':['d1'],'selectedNew':[]}}),after=dict(report=None,contexts={}))
    assert versions.compare(sid,'v1','v1','stage7')['same'] is True
