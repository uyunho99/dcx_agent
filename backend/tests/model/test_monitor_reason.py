"""Monitor status preserves saved explanations and formats failure reasons."""
import socket
from copy import deepcopy

import pytest

from app.routers import training_v2


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail('Model status tests must not access the network')

    monkeypatch.setattr(socket.socket, 'connect', blocked)


@pytest.mark.parametrize('state,detail,saved,error,expected', [
    ('done', {}, '감시 표본 2건을 완료하지 못했습니다.', None,
     '감시 표본 2건을 완료하지 못했습니다.'),
    ('done', {'reason': None}, '저장된 사유', None, '저장된 사유'),
    ('failed', {'reason': '실행 사유'}, '저장된 사유', 'ValueError', '실행 사유'),
    ('failed', {}, '저장된 사유', 'ValueError', '저장된 사유'),
    ('interrupted', {}, '저장된 사유', None, '저장된 사유'),
    ('failed', {}, None, 'ValueError', '감시 중 오류가 났습니다(ValueError).'),
    ('interrupted', {}, None, 'KeyboardInterrupt',
     '감시 중 오류가 났습니다(KeyboardInterrupt).'),
    ('failed', {}, None, None, '감시를 완료하지 못했습니다.'),
    ('interrupted', {}, None, None, '감시를 완료하지 못했습니다.'),
    ('done', {}, None, None, None),
    ('running', {}, None, None, None),
])
def test_monitor_reason_priority(data_dir, monkeypatch, state, detail, saved, error, expected):
    monitor = {'reason': saved, 'sampled': 2, 'errors': [{'reason': 'JevError'}]}
    data = {'schemaVersion': 2, 'version': 'v1',
            'training': {'monitorRunId': 'm', 'monitor': monitor}}
    work = {'runId': 'm', 'kind': 'monitor', 'state': state,
            'detail': detail, 'error': error}
    original = deepcopy(data)
    monkeypatch.setattr(training_v2, 'session', lambda sid, version: data)
    monkeypatch.setattr(training_v2.runner, 'status', lambda sid: [work])

    result = training_v2.status('monitor-session')['monitor']

    assert result['reason'] == expected
    assert result['state'] == state
    assert result['sampled'] == 2
    assert result['errors'] == monitor['errors']
    assert data == original


def test_monitor_without_run_keeps_saved_reason(data_dir, monkeypatch):
    monitor = {'state': 'done', 'reason': '감시 표본 2건을 완료하지 못했습니다.'}
    data = {'schemaVersion': 2, 'version': 'v1', 'training': {'monitor': monitor}}
    monkeypatch.setattr(training_v2, 'session', lambda sid, version: data)
    monkeypatch.setattr(training_v2.runner, 'status', lambda sid: [])

    assert training_v2.status('monitor-session')['monitor'] == monitor
