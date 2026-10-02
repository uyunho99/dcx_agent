"""Locked rounds preserve stored history while the active flow skips R2."""
from copy import deepcopy
import json

import pytest

from app.config import Settings, settings
from app.context import store
from app.keywords import rounds
from app.llm.fake import FakeBackend
from test_rounds_api import backend, client, data_dir, start, commit


def finish_r1(client):
    assert commit(client, 1, start(client, 1)).status_code == 200


def seed_r2(committed=False, needs_regeneration=False):
    kw = {'id': 'old-r2', 'kw': '가짜중복', 'axis': 'physical', 'sub': 'space',
          'round': 2, 'origin': 'llm', 'status': 'approved' if committed else 'pending'}
    patch = {'keywordRounds': {'2': {'round': 2, 'gen': 1,
        'job': {'status': 'done', 'gen': 1}, 'committed': committed,
        'needsRegeneration': needs_regeneration, 'keywords': [kw]}}}
    if committed:
        patch['keywords'] = store.load_session('test')['keywords'] + [kw]
    store.update_session('test', patch)
    return kw


def duplicate_response(backend, monkeypatch):
    original = backend.run
    def run(task):
        if task.task == 'kw_round_3':
            return FakeBackend({task.task: json.dumps({'keywords': [
                {'kw': '가짜중복', 'axis': 'physical', 'sub': 'space', 'why': '상황'},
                {'kw': '새단어', 'axis': 'physical', 'sub': 'space', 'why': '상황'}]})}).run(task)
        return original(task)
    monkeypatch.setattr(backend, 'run', run)


def test_locked_round_rejected(client, monkeypatch):
    finish_r1(client)
    before = store.load_session('test')
    queued = []
    monkeypatch.setattr(rounds, 'execute', queued.append)
    for path, body in [('/rounds/2', None), ('/rounds/2?regenerate=true', None),
                       ('/rounds/2/commit', {'gen': 1, 'decisions': []})]:
        response = client.post('/keywords/test' + path, json=body)
        assert response.status_code == 409
        assert response.json()['error'] == {
            'kind': 'round_locked', 'message': 'R2는 사용하지 않습니다. R1 다음은 R3입니다'}
    assert not queued
    assert store.load_session('test') == before
    assert '2' not in before['keywordRounds']


def test_r3_after_r1(client):
    first = start(client, 1)
    assert client.post('/keywords/test/rounds/3').status_code == 409
    assert commit(client, 1, first).status_code == 200
    assert start(client, 3)['status'] == 'done'


def test_r1_commit_triggers_coverage(client, monkeypatch):
    first = start(client, 1)
    queued = []
    monkeypatch.setattr(rounds, 'execute', queued.append)
    assert commit(client, 1, first).status_code == 200
    saved = store.load_session('test')['coverage']
    assert saved['source'] == 'autocomplete' and saved['status'] == 'loading'
    assert len(queued) == 1
    response = client.post('/keywords/test/rounds/3')
    assert response.status_code == 409
    assert '커버리지를 받는 중입니다' in response.text
    queued[0]()
    monkeypatch.setattr(rounds, 'execute', lambda fn: fn())
    assert store.load_session('test')['coverage']['source'] == 'autocomplete'
    assert start(client, 3)['status'] == 'done'


def test_pending_locked_round_ignored(client, backend, monkeypatch):
    finish_r1(client)
    seed_r2()
    duplicate_response(backend, monkeypatch)
    assert '가짜중복' in [k['kw'] for k in start(client, 3)['keywords']]
    before = store.load_session('test')
    assert '2' not in client.get('/keywords/test').json()['keywordRounds']
    assert store.load_session('test') == before
    assert '2' in before['keywordRounds']


def test_pending_locked_round_hidden_in_version_view(client):
    finish_r1(client)
    seed_r2()
    before = store.load_session('test')
    version = before['version']
    response = client.get(f'/keywords/test?version={version}')
    assert response.status_code == 200
    assert '2' not in response.json()['keywordRounds']
    assert store.load_session('test') == before


@pytest.mark.parametrize('event_type', ['approve', 'reject', 'move', 'unreject'])
def test_events_with_pending_locked_round(client, event_type):
    finish_r1(client)
    saved = store.load_session('test')
    target = saved['keywordRounds']['1']['keywords'][0]
    initial_status = 'rejected' if event_type in ('approve', 'unreject') else 'approved'
    for keywords in (saved['keywords'], saved['keywordRounds']['1']['keywords']):
        for kw in keywords:
            if kw['id'] == target['id']:
                kw.update(status=initial_status, reject={'tags': ['old'], 'note': 'old'}
                          if initial_status == 'rejected' else None)
    pending = {'id': 'k_r2g1_0001', 'kw': '가짜중복', 'axis': 'physical',
               'sub': 'space', 'round': 2, 'origin': 'llm', 'status': 'pending'}
    saved['keywordRounds']['2'] = {'round': 2, 'gen': 1,
        'job': {'status': 'done', 'gen': 1}, 'committed': False, 'keywords': [pending]}
    store.update_session('test', saved)
    before = store.read_json(store.session_dir('test') / 'session.json')
    body = {'round': 1, 'type': event_type, 'kwId': target['id']}
    if event_type == 'move':
        body['to'] = {'axis': 'psychological', 'sub': 'emotion'}
    elif event_type == 'reject':
        body.update(tags=['irrelevant'], note='범위 밖')
    response = client.post('/keywords/test/events', json=body)
    assert response.status_code == 200, response.text
    after = store.read_json(store.session_dir('test') / 'session.json')
    assert after['keywordRounds']['2'] == before['keywordRounds']['2']
    assert after['keywordRounds']['2']['keywords'][0]['status'] == 'pending'
    for keywords in (after['keywords'], after['keywordRounds']['1']['keywords']):
        updated = next(kw for kw in keywords if kw['id'] == target['id'])
        if event_type == 'move':
            assert (updated['axis'], updated['sub']) == ('psychological', 'emotion')
            assert updated['status'] == initial_status
        else:
            assert updated['status'] == ('rejected' if event_type == 'reject' else 'approved')
            assert updated['reject'] == ({'tags': ['irrelevant'], 'note': '범위 밖'}
                                         if event_type == 'reject' else None)


def test_committed_locked_round_kept(client, backend, monkeypatch):
    finish_r1(client)
    kw = seed_r2(committed=True)
    duplicate_response(backend, monkeypatch)
    saved = client.get('/keywords/test').json()
    assert saved['keywordRounds']['2']['committed'] is True
    assert kw in saved['keywords']
    third = start(client, 3)
    assert '가짜중복' not in [k['kw'] for k in third['keywords']]
    assert commit(client, 3, third).status_code == 200
    assert commit(client, 4, start(client, 4)).status_code == 200


def test_committed_locked_round_not_regenerable_after_restart(client):
    finish_r1(client)
    seed_r2(committed=True, needs_regeneration=True)
    before = store.load_session('test')
    for suffix in ('', f"?version={before['version']}"):
        assert client.get('/keywords/test' + suffix).json()['keywordRounds']['2']['needsRegeneration'] is False
    response = client.post('/keywords/test/rounds/2?regenerate=true')
    assert response.status_code == 409
    assert response.json()['error']['kind'] == 'round_locked'
    assert store.load_session('test') == before
    assert start(client, 3)['status'] == 'done'


def test_r1_recommit_then_r3_regenerates(client):
    finish_r1(client)
    seed_r2(committed=True)
    assert commit(client, 3, start(client, 3)).status_code == 200
    store.update_session('test', {'keywordRounds': {'1': {'needsRegeneration': True}}})
    first = start(client, 1)
    assert store.load_session('test')['keywordRounds']['1']['replacing'] is True
    assert commit(client, 1, first).status_code == 200
    saved = store.load_session('test')['keywordRounds']
    assert saved['2']['needsRegeneration'] and saved['3']['needsRegeneration']
    assert start(client, 3)['status'] == 'done'


def test_unlocked_setting_restores_r2(client, monkeypatch):
    monkeypatch.setattr(settings, 'keyword_locked_rounds', [])
    finish_r1(client)
    assert not store.load_session('test').get('coverage')
    assert client.post('/keywords/test/rounds/3').status_code == 409
    second = start(client, 2)
    assert '2' in client.get('/keywords/test').json()['keywordRounds']
    assert commit(client, 2, second).status_code == 200
    assert store.load_session('test')['coverage']['source'] == 'autocomplete'
    assert start(client, 3)['status'] == 'done'


def test_locked_helpers(monkeypatch):
    assert rounds.locked(2) is True
    assert rounds.locked(1) is False
    assert rounds.previous_round(3) == 1
    assert rounds.previous_round(4) == 3
    assert rounds.previous_round(1) is None
    source = {'1': {'committed': False}, '2': {'committed': True, 'needsRegeneration': True}}
    before = deepcopy(source)
    assert rounds.visible_rounds(source)['2']['needsRegeneration'] is False
    assert source == before
    assert rounds.visible_rounds({'2': {'committed': False}}) == {}
    monkeypatch.setattr(settings, 'keyword_locked_rounds', [])
    assert rounds.previous_round(3) == 2
    assert rounds.visible_rounds(source) == source
    monkeypatch.setenv('KEYWORD_LOCKED_ROUNDS', '[]')
    assert Settings(_env_file=None).keyword_locked_rounds == []
    monkeypatch.setenv('KEYWORD_LOCKED_ROUNDS', '[2, 3]')
    assert Settings(_env_file=None).keyword_locked_rounds == [2, 3]
