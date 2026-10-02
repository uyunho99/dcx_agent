"""Stage-eight HTTP contract with real local persona generation."""
from types import SimpleNamespace

import pytest

from app.context import store as sessions
from app.context.versions import create_version
from app.persona import pipeline
from app.persona.store import PersonaStore
from app.work import runner
from tests.persona.test_pipeline import setup


@pytest.fixture
def api(client, setup, monkeypatch):
    ctx, root, fake = setup
    calls, works = [], []
    def start(sid, version, kind, args):
        calls.append((kind, args))
        if kind == 'persona':
            pipeline.run(SimpleNamespace(**{**vars(ctx), 'args': args}))
        return {'runId': 'worker-1'}
    monkeypatch.setattr(runner, 'start', start)
    monkeypatch.setattr(runner, 'status', lambda sid: works)
    return SimpleNamespace(client=client, sid=ctx.sid, root=root, calls=calls, works=works,
                           store=PersonaStore.open(ctx.sid, 'v1'))


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def error(response, status, kind):
    assert response.status_code == status, response.text
    assert response.json()['status'] == 'error'
    assert response.json()['error']['kind'] == kind
    return response.json()['error']


def generate(api):
    assert ok(api.client.post(f'/persona/{api.sid}/run', json={})) == {'runId': 'worker-1'}


def test_run_409_without_package(api):
    (api.root / 'evidence/package.json').unlink()
    result = error(api.client.post(f'/persona/{api.sid}/run'), 409, 'evidence_required')
    assert result['message'] == '근거 탐색을 마친 뒤 페르소나를 만들 수 있습니다.'
    assert not api.calls


def test_persona_routes(api):
    base = f'/persona/{api.sid}'
    assert ok(api.client.get(base + '/status')) == dict(package=True, evidence_required=False, status='none', run=None, progress=0, personas=[])
    for suffix in ('cards', 'cards/missing', 'map', 'tree'):
        error(api.client.get(base + '/' + suffix), 409, 'not_ready')
    generate(api)
    cards = ok(api.client.get(base + '/cards'))
    assert cards['package_run'] and len(cards['personas']) == 4
    for pid, card in cards['personas'].items():
        assert ok(api.client.get(base + '/cards/' + pid)) == card
        assert card['card']['persona_id'] == pid
        assert {'grades', 'trace', 'prescription', 'scope'} <= card.keys()
    status = ok(api.client.get(base + '/status'))
    assert status['status'] == 'done' and status['run'] == cards['run']
    assert all(p['error'] is None for p in status['personas'])
    assert status['stage8']['cards'] == 4
    assert 'context_id' in ok(api.client.get(base + '/map'))['points'][0]
    assert ok(api.client.get(base + '/tree')) == api.store.read('tree')
    error(api.client.post(base + '/cards/CL0-P0/retry', json={'run': 'old'}), 409, 'stale_run')
    retried = ok(api.client.post(base + '/cards/CL0-P0/retry', json={'run': cards['run']}))
    assert retried['run'] != cards['run']
    assert api.calls[-1] == ('persona', {'run': cards['run'], 'personas': ['CL0-P0']})


def test_running_and_locked(api):
    api.works.append(dict(kind='persona', version='v1', state='running', progress=.2))
    error(api.client.post(f'/persona/{api.sid}/run'), 409, 'running')
    api.works[0]['kind'] = 'insight'
    error(api.client.post(f'/persona/{api.sid}/run'), 409, 'locked')
    assert not api.calls


def test_insight_routes(api, monkeypatch):
    base = f'/insight/{api.sid}'
    error(api.client.post(base + '/run', json={'mode': 'derive'}), 409, 'persona_required')
    empty = ok(api.client.get(base))
    assert empty == dict(insights=dict(revision=0, items=[], history=[]),
                         concepts=dict(revision=0, items=[], history=[]), bars=None, radar=None,
                         worker=dict(status='idle', reason=None, runId=None, mode=None, target=None))
    generate(api)
    assert ok(api.client.post(base + '/run', json={'mode': 'derive'})) == {'runId': 'worker-1'}
    item = dict(id='I1', title='Title', pain_point='Pain', context_ids=['C1'], known_ki_id=None,
                odi=4, opportunity_mean=4, default_target=True, radar={'raw': {'Computed': .5}})
    api.store.new_revision('insights', [item], by='generate', message=None)
    response = ok(api.client.get(base))
    assert response['insights']['items'] == [item]
    assert response['bars'] == dict(bars=[{'id': 'I1', 'odi': 4}], mean=4, targets=['I1'])
    assert response['radar'] == {'I1': item['radar']}
    assert ok(api.client.post(base + '/concept/I1')) == {'runId': 'worker-1'}
    assert api.calls[-1] == ('insight', {'mode': 'concept', 'target': 'I1'})
    error(api.client.post(base + '/concept/missing'), 400, 'validation')
    from app.persona import chat
    seen = []
    monkeypatch.setattr(chat, 'edit', lambda *a: seen.append(a) or {'ok': True, 'revision': 2})
    assert ok(api.client.post(base + '/chat', json={'target': 'insights', 'message': 'edit'})) == {'ok': True, 'revision': 2}
    assert seen == [(api.sid, 'v1', 'insights', 'edit')]
    assert ok(api.client.post(base + '/revert', json={'target': 'insights', 'revision': 1})) == {'revision': 2}
    error(api.client.post(base + '/revert', json={'target': 'insights', 'revision': 999}), 404, 'not_found')
    assert ok(api.client.put(base + '/confirm', json={'ids': ['I1', 'I1']})) == {'confirmed': ['I1']}
    assert sessions.load_session(api.sid)['insight']['confirmed'] == ['I1']
    error(api.client.put(base + '/confirm', json={'ids': ['missing']}), 400, 'validation')


@pytest.mark.parametrize('method,path,body', [
    ('post', '/persona/{sid}/run', {}),
    ('post', '/persona/{sid}/cards/CL0-P0/retry', {'run': 'old'}),
    ('post', '/insight/{sid}/run', {'mode': 'derive'}),
    ('post', '/insight/{sid}/concept/I1', None),
    ('post', '/insight/{sid}/chat', {'target': 'insights', 'message': 'edit'}),
    ('post', '/insight/{sid}/revert', {'target': 'insights', 'revision': 1}),
    ('put', '/insight/{sid}/confirm', {'ids': []}),
])
def test_readonly_writes(api, method, path, body):
    generate(api)
    create_version(api.sid, 'v1', 'stage8', '')
    response = getattr(api.client, method)(path.format(sid=api.sid) + '?version=v1', json=body)
    assert response.status_code == 409
    assert ok(api.client.get(f'/persona/{api.sid}/cards?version=v1'))['personas']


def test_insight_checks_changed_source_without_status_poll(api):
    generate(api)
    package = sessions.read_json(api.root / 'evidence/package.json')
    package['params']['CONCURRENCY'] = 99  # changed producer package
    sessions.write_json(api.root / 'evidence/package.json', package)
    error(api.client.post(f'/insight/{api.sid}/run', json={'mode': 'derive'}), 409, 'stale')


def test_pending_cards_and_worker_status(api):
    api.store.write('cards', {'run': 'pending-run', 'personas': {'P1': {'status': 'pending'}}})
    base = f'/persona/{api.sid}'
    assert ok(api.client.get(base + '/cards/P1')) == {'status': 'pending', 'card': None}
    # No source reconciliation required for this worker projection check.
    api.store.path.joinpath('cards.json').unlink()
    api.works.append(dict(kind='persona', version='v1', state='interrupted', progress=.4))
    assert ok(api.client.get(base + '/status'))['status'] == 'interrupted'
    error(api.client.post(base + '/run', json={'personas': ['missing']}), 400, 'validation')


def test_insight_conflicts_failure_and_concept_revert(api):
    generate(api)
    base = f'/insight/{api.sid}'
    api.works.append(dict(kind='insight', version='v1', state='paused', progress=0))
    error(api.client.post(base + '/run', json={'mode': 'derive'}), 409, 'running')
    api.works[0]['kind'] = 'persona'
    error(api.client.post(base + '/run', json={'mode': 'derive'}), 409, 'locked')
    api.works.clear()
    assert ok(api.client.post(base + '/chat', json={'target': 'insights', 'message': 'edit'})) == {
        'ok': False, 'message': '요청을 반영하지 못했습니다. 다르게 말해 주세요.'}
    api.store.new_revision('concepts', [{'id': 'I1', 'basis': 'original'}], by='generate', message=None)
    api.store.new_revision('concepts', [{'id': 'I1', 'basis': 'changed'}], by='chat', message='edit')
    assert ok(api.client.post(base + '/revert', json={'target': 'concept:I1', 'revision': 1})) == {'revision': 3}
    assert ok(api.client.get(base))['concepts']['items'][0]['basis'] == 'original'
    error(api.client.post(base + '/revert', json={'target': 'concept:missing', 'revision': 1}), 404, 'not_found')
    error(api.client.post(base + '/chat', json={'target': '../../cards', 'message': 'edit'}), 422, 'validation')


@pytest.mark.parametrize('status,stale', [('partial', {}), ('running', {}), ('done', {'stage7': 'changed'})])
def test_unready_evidence_refuses_run_and_retry(api, status, stale):
    generate(api)
    cards = api.store.read('cards')
    sessions.update_session(api.sid, {'evidence': {'status': status}, 'stale': stale})
    for suffix, body in [('/run', {}), ('/cards/CL0-P0/retry', {'run': cards['run']})]:
        result = error(api.client.post(f'/persona/{api.sid}' + suffix, json=body), 409, 'evidence_required')
        assert result['message'] == '근거 탐색을 마친 뒤 페르소나를 만들 수 있습니다.'
    status = ok(api.client.get(f'/persona/{api.sid}/status'))
    assert status['package'] is False and status['evidence_required'] is True


def test_segment_reset_identical_reconfirmation_is_not_current(api):
    from app.segment.pipeline import _session
    from app.persona.package import load_package
    from app.routers.sessions import _completion
    generate(api)
    package = (api.root / 'evidence/package.json').read_bytes()
    evidence = sessions.load_session(api.sid)['evidence']
    _session(api.sid, 'v1', {'status': 'done'}, reset=True)
    sessions.update_session(api.sid, {'evidence': {**evidence, 'status': 'stale'}})
    from app.segment.store import SegmentStore
    seg = SegmentStore.open(api.sid, 'v1')
    for row in seg.personas():
        seg.confirm('personas', row['persona_id'], {'name': row['name'], 'desire': row['desire']})
    for row in seg.contexts():
        seg.confirm('contexts', row['context_id'], {'name': row['name'], 'action': row['action']})
    # Identical re-confirmation cannot make retained evidence current.
    assert pipeline._confirmed_matches(api.sid, 'v1', load_package(api.sid, 'v1'))
    assert (api.root / 'evidence/package.json').read_bytes() == package
    assert not _completion(api.sid, sessions.load_session(api.sid), 'v1')['personaDone']
    assert pipeline.mark_stale_if_changed(api.sid, 'v1')
    assert ok(api.client.get(f'/persona/{api.sid}/status'))['status'] == 'stale'


def test_invalid_package_has_korean_error_and_safe_reads(api):
    generate(api)
    path = api.root / 'evidence/package.json'
    package = sessions.read_json(path)
    package['projectContext'] = {}
    sessions.write_json(path, package)
    result = error(api.client.post(f'/persona/{api.sid}/run'), 409, 'evidence_required')
    assert '근거 탐색' in result['message']
    assert ok(api.client.get(f'/persona/{api.sid}/status'))['package'] is False
    cards = api.store.read('cards')
    cards['personas']['CL0-P0']['status'] = 'failed'
    api.store.write('cards', cards)
    ok(api.client.get(f'/persona/{api.sid}/cards'))
