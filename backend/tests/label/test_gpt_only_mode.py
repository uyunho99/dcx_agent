import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, settings
from app.context import store, versions
from app.label import jev, judge
from app.routers import labeling_v2

MESSAGE = 'Jev가 연결되지 않아 GPT 단독으로 판정합니다.'


@pytest.mark.parametrize('value, expected', [(None, False), ('', False), ('true', True)])
def test_fake_cross_setting(monkeypatch, value, expected):
    monkeypatch.delenv('LABEL_FAKE_JEV_CROSS', raising=False)
    if value is not None:
        monkeypatch.setenv('LABEL_FAKE_JEV_CROSS', value)
    assert Settings(_env_file=None).label_fake_jev_cross is expected


@pytest.mark.parametrize('backend,keys,opt_in,expected', [
    ('fake', [], False, 'gpt_only'),
    ('http', [], False, 'gpt_only'),
    ('http', ['offline'], False, 'cross'),
    ('fake', [], True, 'cross'),
    ('fake', ['offline'], False, 'gpt_only'),
])
def test_mode_preview(monkeypatch, backend, keys, opt_in, expected):
    monkeypatch.setattr(settings, 'jev_backend', backend)
    monkeypatch.setattr(settings, 'jev_api_keys', keys)
    monkeypatch.setattr(settings, 'label_fake_jev_cross', opt_in)
    assert jev.jev_available() is (expected == 'cross')
    assert jev.labeler_mode({}) == expected


def test_started_old_session_is_cross(monkeypatch):
    monkeypatch.setattr(settings, 'jev_backend', 'fake')
    assert jev.labeler_mode({'labeling': {'started': True}}) == 'cross'


@pytest.fixture
def client(data_dir):
    app = FastAPI()
    app.include_router(labeling_v2.router)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def prepared(data_dir, monkeypatch):
    monkeypatch.setattr(settings, 'jev_backend', 'fake')
    monkeypatch.setattr(settings, 'jev_api_keys', [])
    monkeypatch.setattr(settings, 'label_fake_jev_cross', False)
    sid = 'gptonly'
    store.update_session(sid, {'schemaVersion': 2, 'prep': {'status': 'done',
        'derivedRef': {'collectionId': 'c1', 'prepKey': 'p_123456789abc'}}})
    data = store.load_session(sid)
    data['projectContext'] = {'oneLiner': '테스트 정의'}
    store.write_json(store.session_dir(sid) / 'session.json', data)
    root = data_dir / f'derived/{sid}/c1/p_123456789abc/docs'
    root.mkdir(parents=True)
    (root / 'part.jsonl').write_text(json.dumps({'doc_id': 'd', 'body': '본문'}))
    calls = []

    def start(s, v, kind, args):
        locked = store.load_session(s)['labeling']
        assert locked['started'] is True
        assert locked['labelerMode'] == 'gpt_only'
        calls.append(args['labeler'])
        return {'runId': args['labeler'], 'state': 'running'}

    monkeypatch.setattr(labeling_v2.runner, 'start', start)
    return sid, calls


def test_start_persists_gpt_only_and_keeps_mode(client, prepared, monkeypatch):
    sid, calls = prepared
    response = client.post(f'/label/{sid}/start')
    assert response.status_code == 200
    assert set(response.json()['workers']) == {'gpt'}
    data = store.load_session(sid)
    assert data['labeling']['labelerMode'] == 'gpt_only'
    assert data['labeling']['judgeRuns'] == {'gpt': 'gpt'}
    assert calls == ['gpt']
    monkeypatch.setattr(settings, 'jev_backend', 'http')
    monkeypatch.setattr(settings, 'jev_api_keys', ['offline'])
    assert jev.labeler_mode(data) == 'gpt_only'
    assert set(client.post(f'/label/{sid}/start').json()['workers']) == {'gpt'}


@pytest.mark.parametrize('action', ['pause', 'resume', 'stop'])
def test_jev_control_rejected(client, prepared, action):
    sid, _ = prepared
    store.update_session(sid, {'labeling': {'started': True, 'labelerMode': 'gpt_only'}})
    response = client.post(f'/label/{sid}/judge/jev/{action}')
    assert response.status_code == 409
    assert response.json()['error']['message'] == MESSAGE


def test_jev_worker_rejected_before_work(data_dir):
    store.write_json(versions.version_dir('guard', 'v1') / 'session.json',
                     {'labeling': {'started': True, 'labelerMode': 'gpt_only'}})
    ctx = SimpleNamespace(sid='guard', version='v1', args={'labeler': 'jev'})
    with pytest.raises(ValueError, match=MESSAGE):
        judge.run_worker(ctx)


@pytest.mark.parametrize('backend,keys,opt_in', [
    ('http', ['offline'], False),
    ('fake', [], True),
])
def test_cross_start_creates_both_runs(client, prepared, monkeypatch, backend, keys, opt_in):
    sid, _ = prepared
    monkeypatch.setattr(settings, 'jev_backend', backend)
    monkeypatch.setattr(settings, 'jev_api_keys', keys)
    monkeypatch.setattr(settings, 'label_fake_jev_cross', opt_in)
    calls = []

    def start(s, v, kind, args):
        assert store.load_session(s)['labeling']['labelerMode'] == 'cross'
        calls.append(args['labeler'])
        return {'runId': args['labeler'], 'state': 'running'}

    monkeypatch.setattr(labeling_v2.runner, 'start', start)
    response = client.post(f'/label/{sid}/start')
    assert response.status_code == 200
    assert set(response.json()['workers']) == {'jev', 'gpt'}
    assert calls == ['jev', 'gpt']
    assert store.load_session(sid)['labeling']['judgeRuns'] == {'jev': 'jev', 'gpt': 'gpt'}
    monkeypatch.setattr(settings, 'jev_api_keys', [])
    monkeypatch.setattr(settings, 'label_fake_jev_cross', False)
    assert jev.labeler_mode(store.load_session(sid)) == 'cross'
