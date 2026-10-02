"""Stage-six HTTP contract, using the real synchronous synthetic pipeline."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.config import settings
from app.context import store as sessions
from app.context.versions import create_version, version_dir
from app.llm import registry
from app.segment import pipeline
from app.segment.store import SegmentStore
from app.work import runner
from tests.fixtures.segment_synth import make_segment_session, fake_dims_backend


@pytest.fixture
def api(client, data_dir, monkeypatch):
    monkeypatch.setattr(settings, 'embed_backend', 'fake')
    monkeypatch.setattr(settings, 'llm_backend', 'fake')
    monkeypatch.setattr(registry, 'get_backend', lambda name: SimpleNamespace(
        run=lambda task: fake_dims_backend([a.title for a in task.attachments]).run(task)))
    fixture = make_segment_session(data_dir, docs_per_context=4)
    calls, works, held = [], [], []
    original_lock = sessions.locked

    @contextmanager
    def lock(sid):
        with original_lock(sid):
            held.append(True)
            try:
                yield
            finally:
                held.pop()

    monkeypatch.setattr(sessions, 'locked', lock)

    def start(sid, version, kind, args):
        assert not held, 'Never run long work under the session lock'
        assert kind == 'segment'
        calls.append(args)
        pipeline.run(SimpleNamespace(sid=sid, version=version, args=args,
                                    heartbeat=lambda *a: None, should_stop=lambda: False))
        work = dict(runId=f'worker-{len(calls)}', version=version, kind=kind,
                    state='done', progress=1, detail={'step': 'drafts'})
        works.append(work)
        return work

    monkeypatch.setattr(runner, 'start', start)
    monkeypatch.setattr(runner, 'status', lambda sid: works)
    return SimpleNamespace(client=client, sid=fixture.sid, base=f'/segment/{fixture.sid}',
                           store=SegmentStore.open(fixture.sid, 'v1'), calls=calls, works=works)


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def error(response, status, kind=None):
    assert response.status_code == status, response.text
    body = response.json()
    assert body['status'] == 'error'
    assert body['error']['message']
    if kind:
        assert body['error']['kind'] == kind
    return body['error']


def run(api):
    return ok(api.client.post(api.base + '/run', json={}))


def payload(api, layer):
    return dict(run=api.store.get_run(), name='확정 이름', confirm=True,
                **({'desire': '편하게 지내고 싶다', 'goals': ['시간 절약']} if layer == 'personas' else
                   {'action': '예약한다'} if layer == 'contexts' else {}))


def confirm(api, layer):
    key = {'clusters': 'cluster_id', 'personas': 'persona_id', 'contexts': 'context_id'}[layer]
    for row in getattr(api.store, layer)():
        result = ok(api.client.put(f'{api.base}/{layer}/{row[key]}', json=payload(api, layer)))
        assert result['id'] == row[key] and result['confirmed'] and result['name'] == '확정 이름'


def test_run_status_and_cluster_list(api):
    assert ok(api.client.get(api.base + '/status'))['status'] == 'none'
    assert run(api)['runId'] == 'worker-1'
    assert api.calls == [{'k': None, 'fresh': False}]
    state = ok(api.client.get(api.base + '/status'))
    assert state['run'] == api.store.get_run() == state['stage6']['run']
    assert state['status'] == 'review' and state['step'] == 'drafts' and state['progress'] == 1
    assert state['confirm']['clusters'] == f'0/{len(api.store.clusters())}'
    listing = ok(api.client.get(api.base + '/clusters'))
    assert listing['run'] == state['run'] and listing['kSuggest']['k']
    assert {'id', 'docs', 'nameDraft', 'name', 'confirmed', 'keywords', 'reps', 'quality',
            'channels', 'channelSkew', 'requests'} <= listing['clusters'][0].keys()
    assert sum(c['docs'] for c in listing['clusters']) == len(api.store.docs(limit=10000))
    confirm(api, 'clusters')
    assert sessions.load_session(api.sid)['segment']['confirm']['clusters'] == f'{len(listing["clusters"])}/{len(listing["clusters"])}'


def test_run_reset_required(api):
    error(api.client.post(api.base + '/run', json={'k': 3}), 409, 'confirm_required')
    assert not api.calls
    run(api)
    confirm(api, 'clusters')
    for body in ({}, {'k': 3}):
        error(api.client.post(api.base + '/run', json=body), 409, 'confirm_required')
    assert len(api.calls) == 1
    ok(api.client.post(api.base + '/run', json={'confirmReset': True}))
    assert api.calls[-1] == {'k': None, 'fresh': True}
    assert all(not row['confirmed_at'] for row in api.store.clusters())


@pytest.mark.parametrize(('segment_status', 'work_state'), [
    ('interrupted', 'interrupted'), ('failed', 'failed'), ('stopped', 'done'),
    ('running', 'interrupted'), ('review', 'failed'),
])
def test_interrupted_or_failed_run_resumes_and_keeps_confirmations(api, segment_status, work_state):
    run(api)
    confirm(api, 'clusters')
    confirm(api, 'personas')
    cid = api.store.contexts()[0]['context_id']
    ok(api.client.put(f'{api.base}/contexts/{cid}', json=payload(api, 'contexts')))
    before = {layer: getattr(api.store, layer)() for layer in ('clusters', 'personas', 'contexts')}
    old_run = api.store.get_run()
    root = version_dir(api.sid, 'v1')
    # Model a stop after layer publication, before the last checkpoint completes.
    checkpoint = sessions.read_json(root / 'segment/checkpoint.json')
    checkpoint['done'].remove('drafts')
    sessions.write_json(root / 'segment/checkpoint.json', checkpoint)
    data = sessions.load_session(api.sid)
    data['segment']['status'] = segment_status
    sessions.write_json(root / 'session.json', data)
    api.works[-1]['state'] = work_state

    error(api.client.post(api.base + '/run', json={'k': 3}), 409, 'confirm_required')
    assert run(api)['runId'] == 'worker-2'
    assert api.calls[-1] == {'k': None, 'fresh': False}
    assert api.store.get_run() != old_run
    for layer, rows in before.items():
        after = getattr(api.store, layer)()
        for old, new in zip(rows, after, strict=True):
            for field in ('confirmed_at', 'name', 'desire', 'goals', 'action'):
                assert new.get(field) == old.get(field)


@pytest.mark.parametrize('state', ['running', 'paused'])
@pytest.mark.parametrize('body', [{}, {'confirmReset': True}, {'k': 3}])
def test_running_run_returns_conflict(api, state, body):
    run(api)
    api.works[-1]['state'] = state
    result = error(api.client.post(api.base + '/run', json=body), 409, 'running')
    assert result['message'] == '클러스터링이 이미 진행 중입니다.'
    assert len(api.calls) == 1


@pytest.mark.parametrize('state', ['review', 'done'])
def test_completed_run_requires_reset_confirmation(api, state):
    run(api)
    data = sessions.load_session(api.sid)
    data['segment']['status'] = state
    sessions.write_json(version_dir(api.sid, 'v1') / 'session.json', data)
    error(api.client.post(api.base + '/run', json={}), 409, 'confirm_required')
    assert len(api.calls) == 1


def test_stage5_missing(api):
    data = sessions.load_session(api.sid)
    data['training'] = {}
    sessions.write_json(version_dir(api.sid, 'v1') / 'session.json', data)
    result = error(api.client.post(api.base + '/run', json={}), 409)
    assert result['message'] == '학습 단계에서 결과를 저장한 뒤 클러스터링을 실행하세요.'
    assert not api.calls


def test_layer_gating_and_list_shapes(api):
    run(api)
    p, c = api.store.personas()[0], api.store.contexts()[0]
    for layer, item in [('personas', p['persona_id']), ('contexts', c['context_id'])]:
        error(api.client.get(f'{api.base}/{layer}'), 409, 'locked')
        error(api.client.put(f'{api.base}/{layer}/{item}', json=payload(api, layer)), 409, 'locked')
    error(api.client.post(f'{api.base}/personas/{p["persona_id"]}/confirm-contexts',
        json={'run': api.store.get_run(), 'contexts': [{'id': c['context_id'], 'name': '이름', 'action': '행동'}]}), 409, 'locked')
    first = api.store.clusters()[0]['cluster_id']
    ok(api.client.put(f'{api.base}/clusters/{first}', json=payload(api, 'clusters')))
    error(api.client.get(f'{api.base}/personas?cluster={first}'), 409, 'locked')
    confirm(api, 'clusters')
    listing = ok(api.client.get(f'{api.base}/personas?cluster={p["cluster_id"]}'))
    assert listing['run'] == api.store.get_run()
    assert all(r['clusterId'] == p['cluster_id'] for r in listing['personas'])
    assert {'docs', 'authors', 'nameDraft', 'desireDraft', 'goalsDraft', 'centrality',
            'network', 'similar', 'reps', 'flags', 'confirmed'} <= listing['personas'][0].keys()
    error(api.client.get(api.base + '/contexts'), 409, 'locked')
    confirm(api, 'personas')
    listing = ok(api.client.get(f'{api.base}/contexts?persona={p["persona_id"]}'))
    assert listing['run'] == api.store.get_run() and 'emptyGoalConstraintRatio' in listing
    assert all(r['personaId'] == p['persona_id'] for r in listing['contexts'])
    assert {'docs', 'nameDraft', 'actionDraft', 'action', 'keywords', 'dominantConstraint',
            'dimsSummary', 'quality', 'flags', 'confirmed'} <= listing['contexts'][0].keys()


@pytest.mark.parametrize('bad', [{'desire': ''}, {'desire': '   '}, {'goals': []},
                                {'goals': ['1', '2', '3', '4']}, {'goals': [' ']}])
def test_persona_validation(api, bad):
    run(api)
    confirm(api, 'clusters')
    pid = api.store.personas()[0]['persona_id']
    error(api.client.put(f'{api.base}/personas/{pid}', json={**payload(api, 'personas'), **bad}), 422, 'validation')
    assert not api.store.personas()[0]['confirmed_at']


def test_context_confirm_and_bulk_atomic_completion(api):
    run(api)
    confirm(api, 'clusters')
    confirm(api, 'personas')
    rows = api.store.contexts()
    first, other = rows[0], next(c for c in rows if c['persona_id'] != rows[0]['persona_id'])
    items = [{'id': r['context_id'], 'name': '문맥', 'action': '예약한다'} for r in [first, other]]
    endpoint = f'{api.base}/personas/{first["persona_id"]}/confirm-contexts'
    error(api.client.post(endpoint, json={'run': api.store.get_run(), 'contexts': items}), 422)
    assert all(not r['confirmed_at'] for r in api.store.contexts())
    ok(api.client.put(f'{api.base}/contexts/{first["context_id"]}', json=payload(api, 'contexts')))
    assert not sessions.load_session(api.sid).get('completion', {}).get('segmentDone')
    for p in api.store.personas():
        items = [{'id': r['context_id'], 'name': '문맥', 'action': '예약한다'}
                 for r in api.store.contexts(p['persona_id'])]
        result = ok(api.client.post(f'{api.base}/personas/{p["persona_id"]}/confirm-contexts',
            json={'run': api.store.get_run(), 'contexts': items}))
        assert all(r['confirmed'] for r in result['contexts'])
    state = ok(api.client.get(api.base + '/status'))
    assert state['confirm']['contexts'] == f'{len(rows)}/{len(rows)}'
    assert state['status'] == sessions.load_session(api.sid)['segment']['status'] == 'done'
    assert sessions.load_session(api.sid)['completion']['segmentDone'] is True


def test_stale_run_rejected(api):
    run(api)
    old = api.store.get_run()
    confirm(api, 'clusters')
    ok(api.client.post(api.base + '/run', json={'k': 3, 'confirmReset': True}))
    assert api.calls[-1] == {'k': 3, 'fresh': True} and old != api.store.get_run()
    for layer, key in [('clusters', 'cluster_id'), ('personas', 'persona_id'), ('contexts', 'context_id')]:
        item = getattr(api.store, layer)()[0][key]
        result = error(api.client.put(f'{api.base}/{layer}/{item}', json={**payload(api, layer), 'run': old}), 409, 'stale_run')
        assert result['message'] == '다른 화면에서 다시 나눠 결과가 바뀌었습니다. 새로고침하세요.'
        assert all(not r['confirmed_at'] and r['name'] is None for r in getattr(api.store, layer)())
        missing = payload(api, layer)
        del missing['run']
        error(api.client.put(f'{api.base}/{layer}/{item}', json=missing), 422, 'validation')
    c = api.store.contexts()[0]
    endpoint = f'{api.base}/personas/{c["persona_id"]}/confirm-contexts'
    items = [{'id': c['context_id'], 'name': 'old', 'action': 'old'}]
    error(api.client.post(endpoint, json={'run': old, 'contexts': items}), 409, 'stale_run')
    error(api.client.post(endpoint, json={'contexts': items}), 422, 'validation')
    assert all(not c['confirmed_at'] for c in api.store.contexts())


def test_requests_and_doc_paging(api):
    run(api)
    cid = api.store.clusters()[0]['cluster_id']
    for kind in ('split', 'merge'):
        body = dict(layer='clusters', id=cid, kind=kind, note='검토해 주세요')
        assert ok(api.client.post(api.base + '/requests', json=body)).items() >= body.items()
    assert len(ok(api.client.get(api.base + '/clusters'))['clusters'][0]['requests']) == 2
    error(api.client.post(api.base + '/requests', json=dict(layer='personas', id=cid, kind='split', note='메모')), 422)
    c = api.store.contexts()[0]['context_id']
    expected = api.store.docs(context_id=c, band='core', offset=1, limit=2)
    page = ok(api.client.get(f'{api.base}/docs?context={c}&band=core&offset=1&limit=2'))
    assert page['run'] == api.store.get_run() and page['offset'] == 1 and page['limit'] == 2
    assert [d['docId'] for d in page['docs']] == [d['doc_id'] for d in expected]
    assert page['total'] == len(api.store.docs(context_id=c, band='core', limit=10000))
    assert all('body' in d and 'comments' in d and d['source'] != 'agreed' for d in page['docs'])
    for query in ('offset=-1', 'limit=-1', 'limit=1001', 'band=bad'):
        error(api.client.get(f'{api.base}/docs?{query}'), 422, 'validation')


def test_readonly_writes_and_version_reads(api):
    run(api)
    old = api.store.get_run()
    create_version(api.sid, 'v1', 'stage7', '')
    for method, suffix, body in [('post', '/run', {'confirmReset': True}),
        *[('put', f'/{layer}/{getattr(api.store, layer)()[0][key]}', payload(api, layer))
          for layer, key in [('clusters', 'cluster_id'), ('personas', 'persona_id'), ('contexts', 'context_id')]],
        ('post', '/requests', dict(layer='clusters', id='CL0', kind='split', note='메모')),
        ('post', f'/personas/{api.store.personas()[0]["persona_id"]}/confirm-contexts',
         {'run': old, 'contexts': [{'id': api.store.contexts()[0]['context_id'], 'name': '문맥', 'action': '행동'}]})]:
        error(getattr(api.client, method)(api.base + suffix + '?version=v1', json=body), 409)
    assert ok(api.client.get(api.base + '/clusters?version=v1'))['run'] == old
    assert ok(api.client.get(api.base + '/status?version=v1'))['run'] == old


def test_worker_failure_status(api):
    run(api)
    api.works[-1].update(state='interrupted', detail={'step': 'L3', 'reason': '이어서 진행'}, progress=.4)
    result = ok(api.client.get(api.base + '/status'))
    assert result['status'] == 'interrupted' and result['reason'] == '이어서 진행'
    assert result['step'] == 'L3' and result['progress'] == .4


def test_generation_change_between_check_and_write_is_rejected(api, monkeypatch):
    from app.routers import segment
    run(api)
    cid = api.store.clusters()[0]['cluster_id']
    body = payload(api, 'clusters')
    original = segment._gate

    def rotate(store, layer):
        original(store, layer)
        api.store.set_run('concurrent-generation')

    monkeypatch.setattr(segment, '_gate', rotate)
    error(api.client.put(f'{api.base}/clusters/{cid}', json=body), 409, 'stale_run')
    assert all(not c['confirmed_at'] and c['name'] is None for c in api.store.clusters())


def test_single_context_confirmations_complete_and_clear_stale(api):
    run(api)
    sessions.update_session(api.sid, {'stale': {'stage6': 'old', 'stage7': 'old'}})
    confirm(api, 'clusters')
    confirm(api, 'personas')
    confirm(api, 'contexts')
    state = sessions.load_session(api.sid)
    assert state['segment']['status'] == 'done' and state['completion']['segmentDone']
    assert 'stage6' not in state['stale'] and state['stale']['stage7'] == 'old'


def test_invalid_run_and_missing_entities(api):
    for body in ({'k': 2}, {'k': 9}, {'k': 3.5}, {'k': True}):
        error(api.client.post(api.base + '/run', json=body), 422, 'validation')
    assert not api.calls
    run(api)
    error(api.client.put(api.base + '/clusters/missing', json=payload(api, 'clusters')), 404, 'not_found')
    error(api.client.post(api.base + '/requests', json=dict(layer='clusters', id='missing', kind='split', note='메모')), 404, 'not_found')
    assert ok(api.client.get(api.base + '/docs?context=missing'))['docs'] == []
    error(api.client.get(api.base + '/status?version=v999'), 404)


def test_generation_on_docs_is_captured_before_rows(api, monkeypatch):
    run(api)
    old = api.store.get_run()
    original = SegmentStore.docs

    def rotate(store, *args, **kwargs):
        rows = original(store, *args, **kwargs)
        api.store.set_run('new-generation')
        return rows

    monkeypatch.setattr(SegmentStore, 'docs', rotate)
    page = ok(api.client.get(api.base + '/docs?limit=1'))
    assert page['run'] == old


@pytest.mark.parametrize('scope', [None, {}, {'note': '가정에서 에어컨을 쓰는 사람'}])
def test_target_scope_hint(api, scope):
    run(api)
    confirm(api, 'clusters')
    path = version_dir(api.sid, 'v1') / 'session.json'
    data = sessions.read_json(path)
    data['projectContext'] = {'targetScope': scope}
    sessions.write_json(path, data)
    rows = ok(api.client.get(api.base + '/personas'))['personas']
    for row in rows:
        if scope:
            assert row['hint'] == '초안 힌트: 0단계 대상 선언 · 가정에서 에어컨을 쓰는 사람'
        else:
            assert not row.get('hint')


def test_status_prefers_korean_reason_and_exposes_detail(api):
    reason = '클러스터링할 문서가 없습니다.'
    sessions.update_session(api.sid, {'segment': {'status': 'failed', 'reason': reason}})
    detail = {'step': 'L3', 'persona': 3, 'personas': 12}
    api.works.append(dict(version='v1', kind='segment', state='failed', error='StoreError', detail=detail))
    state = ok(api.client.get(api.base + '/status'))
    assert state['reason'] == reason
    assert state['detail'] == detail


@pytest.mark.parametrize('layer', ['clusters', 'personas'])
def test_api_caps_legacy_representatives(api, layer):
    api.store.write_layers(
        clusters=[{'cluster_id': 'CL0', 'confirmed_at': 'saved', 'reps': [{'text': 'x'*1000}]}],
        personas=[{'persona_id': 'CL0-P0', 'cluster_id': 'CL0', 'reps': [{'text': 'y'*1000}]}])
    rows = ok(api.client.get(api.base + '/' + layer))[layer]
    assert len(rows[0]['reps'][0]['text']) == 300


@pytest.mark.parametrize('layer', ['clusters', 'personas', 'contexts', 'docs'])
def test_rows_and_generation_share_snapshot(data_dir, monkeypatch, layer):
    from app.routers import segment as routes
    reader = routes.ConfirmationStore.open('snapshot', 'v1')
    writer = SegmentStore.open('snapshot', 'v1')
    reader.write_layers(clusters=[dict(cluster_id='old', confirmed_at='yes')],
                        personas=[dict(persona_id='old', confirmed_at='yes')],
                        contexts=[dict(context_id='old')])
    reader.set_run('old')
    monkeypatch.setattr(routes, '_open', lambda *a: ({}, reader))
    original = reader.get_run
    def interleave():
        run = original()
        with writer._db(write=True) as db:
            db.execute("UPDATE meta SET value='new' WHERE key='run'")
            for table, key in routes.LAYERS.items():
                db.execute(f"UPDATE {table} SET {key}='new'")
            db.execute("INSERT INTO docs(doc_id) VALUES ('new')")
        return run
    monkeypatch.setattr(reader, 'get_run', interleave)
    monkeypatch.setattr(routes, '_report', lambda *a: {})
    monkeypatch.setattr(routes, 'prepared_root', lambda *a: data_dir)
    result = getattr(routes, layer)('snapshot', **({'offset': 0, 'limit': 100} if layer == 'docs' else {}))
    assert result['run'] == 'old'
    if layer == 'docs':
        assert result['docs'] == [] and result['total'] == 0
    else:
        assert [row['id'] for row in result[layer]] == ['old']


def test_personas_reset_after_rows(data_dir, monkeypatch):
    from app.routers import segment as routes
    reader = routes.ConfirmationStore.open('snapshot', 'v1')
    writer = SegmentStore.open('snapshot', 'v1')
    reader.write_layers(clusters=[dict(cluster_id='old', confirmed_at='yes')],
                        personas=[dict(persona_id='old')])
    reader.set_run('old')
    monkeypatch.setattr(routes, '_open', lambda *a: ({}, reader))
    original = routes._rows
    def interleave(*args):
        rows = original(*args)
        writer.set_run('new')
        writer.write_layers(personas=[dict(persona_id='new')])
        return rows
    monkeypatch.setattr(routes, '_rows', interleave)
    result = routes.personas('snapshot')
    assert result['run'] == result['personas'][0]['id'] == 'old'
