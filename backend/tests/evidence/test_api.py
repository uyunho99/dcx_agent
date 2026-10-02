"""Stage-seven HTTP contracts exercised with offline, real pipeline outputs."""
import pytest

from app.context import store as sessions
from app.context.versions import create_version
from app.evidence import pipeline
from app.work import runner
from tests.evidence.test_pipeline import setup
from tests.segment.test_api import ok, error


@pytest.fixture
def api(client, setup, monkeypatch):
    setup.client = client
    setup.base = f'/evidence/{setup.sid}'
    setup.works = []
    setup.starts = []
    def start(sid, version, kind, args):
        setup.starts.append((sid, version, kind, args))
        setup.ctx.args = args
        pipeline.run(setup.ctx)
        return {'runId': 'worker-1'}
    monkeypatch.setattr(runner, 'start', start)
    monkeypatch.setattr(runner, 'status', lambda sid: setup.works)
    return setup


def run(api):
    assert ok(api.client.post(api.base+'/run', json={})) == {'runId': 'worker-1'}
    return api.ev.get_run()


def item_contract(item):
    assert set(item) == {'docId','source','location','quote','text','tags','band','novelty','noveltyReason','knownMatch','rare','role','quoteSource','noveltyShown'}
    assert set(item['quote']) == {'text','start','end','verified'}
    assert set(item['location']) == {'field','idx'}
    assert len(item['text']) <= 600


def test_all_read_paths_and_run(api):
    initial = ok(api.client.get(api.base+'/status'))
    assert initial['status'] == 'none' and initial['run'] is None
    generation = run(api)
    assert api.starts[0] == (api.sid, 'v1', 'evidence', {'fresh': False, 'contexts': None})
    status = ok(api.client.get(api.base+'/status?version=v1'))
    assert status['run'] == generation and status['status'] == 'done'
    assert 'stage7' in status
    assert len(status['contexts']) == 3
    row = status['contexts'][0]
    assert set(row) == {'id','personaId','name','status','coverage','counts','error','knownChanged'}
    assert row['name'] == '예약 냉방' and row['personaId'] == 'p1'
    assert all(type(n) in (int, float) for n in row['counts'].values())
    for tab in ('all','new'):
        detail = ok(api.client.get(api.base+f'/contexts/c0?tab={tab}&version=v1'))
        assert set(detail) == {'context','tab','items','counter','rare','excludedKnown','queries','queryFailed','undifferentiated'}
        assert detail['tab'] == tab
        assert [r['docId'] for r in detail['items']] == [r['doc_id'] for r in api.ev.selected('c0',tab)]
        for item in detail['items'] + detail['counter'] + detail['rare']: item_contract(item)
        assert all(set(q) == {'dim','text','origin'} for q in detail['queries'])
    persona = ok(api.client.get(api.base+'/personas/p1?version=v1'))
    assert set(persona) == {'desireSupport','artifacts'} and persona['desireSupport']
    for item in persona['desireSupport']: item_contract(item)
    package = ok(api.client.get(api.base+'/package?version=v1'))
    assert package['schema'] == 'evidence-package/1' and package['version'] == 'v1'


@pytest.mark.parametrize('state', ['unfinished','unconfirmed','empty'])
def test_run_409_until_6c_confirmed(api, state):
    if state == 'unfinished': sessions.update_session(api.sid, {'segment': {'status':'review'}})
    elif state == 'empty': api.seg.write_layers(contexts=[])
    else:
        with api.seg._db(write=True) as db: db.execute('UPDATE contexts SET confirmed_at=NULL')
    err = error(api.client.post(api.base+'/run', json={}),409,'segment_required')
    assert err['message'] == '6-C Context를 모두 확정한 뒤 근거 탐색을 실행하세요.'
    assert api.starts == []


def test_running_and_locked(api):
    api.works.append(dict(kind='evidence',version='v1',state='running'))
    error(api.client.post(api.base+'/run',json={}),409,'running')
    api.works[:] = [dict(kind='segment',version='v1',state='running')]
    error(api.client.post(api.base+'/run',json={}),409,'locked')
    assert api.starts == []


@pytest.mark.parametrize('state', ['queued','running','failed','skipped'])
def test_context_not_ready_while_pending(api, state):
    api.ev.reset('pending', {})
    api.ev.set_context('c0','p1',state)
    error(api.client.get(api.base+'/contexts/c0'),409,'not_ready')
    error(api.client.get(api.base+'/package'),409,'not_ready')


def test_unknown_and_invalid_requests(api):
    error(api.client.get(api.base+'/contexts/missing'),404,'not_found')
    error(api.client.get(api.base+'/personas/missing'),404,'not_found')
    error(api.client.get('/evidence/missing/status'),404,'not_found')
    error(api.client.get(api.base+'/contexts/c0?tab=bad'),422,'validation')
    error(api.client.post(api.base+'/contexts/c0/skip',json={}),422,'validation')


@pytest.mark.parametrize('action', ['skip','refresh-new'])
def test_stale_ui_actions_409(api, action):
    old = run(api)
    run(api)
    before = api.ev.snapshot()
    error(api.client.post(api.base+f'/contexts/c0/{action}',json={'run':old}),409,'stale_run')
    assert api.ev.snapshot() == before


def test_skip_returns_full_status(api):
    generation = run(api)
    api.ev.set_context('c1','p1','failed',error='failed')
    sessions.update_session(api.sid, {'evidence': {'status':'partial'}})
    result = ok(api.client.post(api.base+'/contexts/c1/skip',json={'run':generation}))
    assert result['status'] == 'done' and result['run'] == generation
    assert next(r for r in result['contexts'] if r['id']=='c1')['status'] == 'skipped'


def test_readonly_version_rejects_writes(api):
    generation = run(api)
    create_version(api.sid, 'v1', 'stage7', '')
    assert ok(api.client.get(api.base+'/status?version=v1'))['run'] == generation
    assert ok(api.client.get(api.base+'/contexts/c0?version=v1'))['items']
    assert ok(api.client.get(api.base+'/personas/p1?version=v1'))['desireSupport']
    assert ok(api.client.get(api.base+'/package?version=v1'))['version'] == 'v1'
    for suffix, body in [('/run',{}),('/contexts/c0/refresh-new',{'run':generation}),('/contexts/c0/skip',{'run':generation})]:
        error(api.client.post(api.base+suffix+'?version=v1',json=body),409,'conflict')


def test_known_add_then_refresh_changes_new_tab(api):
    generation = run(api)
    before = ok(api.client.get(api.base+'/contexts/c0?tab=new'))
    doc = before['items'][0]['docId']
    response = api.client.post(f'/known/{api.sid}',json={'type':'doc','doc_id':doc})
    assert response.status_code == 201, response.text
    assert response.json()['from'] == 'rag'
    status = ok(api.client.get(api.base+'/status'))
    assert all(r['knownChanged'] for r in status['contexts'])
    api.calls.clear()
    refreshed = ok(api.client.post(api.base+'/contexts/c0/refresh-new',json={'run':generation}))
    assert refreshed['tab'] == 'new' and doc not in [r['docId'] for r in refreshed['items']]
    assert refreshed['excludedKnown'] >= 1 and api.calls == []
    assert doc in [r['docId'] for r in ok(api.client.get(api.base+'/contexts/c0?tab=all'))['items']]
    assert not ok(api.client.get(api.base+'/status'))['contexts'][0]['knownChanged']


def test_stale_segment_cannot_start(api):
    sessions.update_session(api.sid, {'stale': {'stage6': True}})
    error(api.client.post(api.base+'/run',json={}),409,'segment_required')
    assert api.starts == []


def test_worker_reason_and_version_isolation(api):
    run(api)
    api.works[:] = [dict(kind='evidence',version='v1',state='interrupted',progress=.5,
                        detail={'reason':'offline'}),
                   dict(kind='evidence',version='v2',state='running',progress=0)]
    result = ok(api.client.get(api.base+'/status?version=v1'))
    assert (result['status'],result['progress'],result['reason']) == ('interrupted',.5,'offline')
    sessions.update_session(api.sid, {'evidence': {'status':'stale'}})
    assert ok(api.client.get(api.base+'/status'))['status'] == 'stale'


def test_quote_less_items_match_nonnullable_contract(api):
    from app.evidence.cache import TagCache, prompt_version
    generation = run(api)
    cache = TagCache.open(api.sid,'p_0123456789ab',prompt_version('tag'))
    tags = cache.get_tags(api.docs)
    for tag in tags.values(): tag['quotes'] = []
    cache.put_tags(tags, 'fake')
    for response in [api.client.get(api.base+'/contexts/c0'),
                     api.client.post(api.base+'/contexts/c0/refresh-new',json={'run':generation})]:
        result = ok(response)
        for item in result['items']:
            item_contract(item)
            assert item['quote'] == {'text':'','start':None,'end':None,'verified':False}


def test_context_response_uses_detached_snapshot(api, monkeypatch):
    from app.evidence.store import EvidenceStore
    run(api)
    expected = [r['doc_id'] for r in api.ev.selected('c0','all')]
    original = EvidenceStore.snapshot
    def snapshot(store):
        result = original(store)
        api.ev.reset('replacement', {})
        return result
    monkeypatch.setattr(EvidenceStore, 'snapshot', snapshot)
    result = ok(api.client.get(api.base+'/contexts/c0'))
    assert [r['docId'] for r in result['items']] == expected


@pytest.mark.parametrize('action', ['skip','refresh-new'])
def test_actions_reject_stage6_invalidation(api, action):
    generation = run(api)
    sessions.update_session(api.sid, {'evidence': {'status':'stale'}})
    error(api.client.post(api.base+f'/contexts/c0/{action}',json={'run':generation}),409,'stale_run')


def test_retry_subset_and_fresh_forwarded(api):
    run(api)
    ok(api.client.post(api.base+'/run?version=v1',json={'fresh':True,'contexts':['c1']}))
    assert api.starts[-1][3] == {'fresh':True,'contexts':['c1']}
    error(api.client.post(api.base+'/run',json={'contexts':['missing']}),404,'not_found')
