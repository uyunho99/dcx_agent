from copy import deepcopy

import pytest

from app.context.store import load_session, update_session, session_dir
from test_api import CTX


def minimal(mode):
    data = deepcopy(CTX) | {'taskMode': mode}
    del data['analysisGoal'], data['positioning']
    if mode == 'explore':
        del data['keyMetrics']
    return data


def test_post_metric_without_positioning(client):
    response = client.post('/context', json=minimal('metric'))
    assert response.status_code == 201
    assert load_session(response.json()['sid'])['projectContext']['taskMode'] == 'metric'


def test_post_explore_minimal(client):
    response = client.post('/context', json=minimal('explore'))
    assert response.status_code == 201
    assert load_session(response.json()['sid'])['projectContext']['taskMode'] == 'explore'


def test_post_metric_without_metric_is_422(client):
    # First establish that the otherwise identical metric request is valid.
    assert client.post('/context', json=minimal('metric')).status_code == 201
    response = client.post('/context', json=minimal('metric') | {'keyMetrics': []})
    assert response.status_code == 422
    assert response.json()['error']['kind'] == 'validation'


def test_patch_legacy_keeps_rules(client):
    sid = client.post('/context', json=CTX).json()['sid']
    update_session(sid, {'projectContext': deepcopy(CTX)})
    assert client.patch('/context/' + sid, json={'oneLiner': '바뀜'}).status_code == 200
    assert load_session(sid)['projectContext']['taskMode'] is None
    response = client.patch('/context/' + sid, json={'keyMetrics': []})
    assert response.status_code == 422 and response.json()['error']['kind'] == 'validation'
    assert client.patch('/context/' + sid, json={'oneLiner': '또'}).status_code == 200
    md = (session_dir(sid) / 'project_context.md').read_text()
    assert '과제 유형' not in md and '생각하는 페르소나' not in md
    assert '- 분석 목표: 니즈탐색' in md and '- 핵심 지표 (방향 지시자, 측정값 아님): 만족\n' in md


@pytest.mark.parametrize('field,value', [('taskMode', 'explore'), ('keyMetrics', [{'name': '새 지표'}]), ('personaSeeds', {'items': [{'text': '보호자'}]}), ('researchQuestion', {'text': '새 질문'}), ('oneLiner', '새 정의')])
def test_warnings_after_r1(client, field, value):
    sid = client.post('/context', json=CTX).json()['sid']
    update_session(sid, {'keywordRounds': {'1': {'status': 'done'}}})
    data = deepcopy(CTX) | {field: value}
    response = client.put('/context/' + sid, json=data)
    assert response.status_code == 200
    assert response.json()['warnings'] == [field + '_changed_after_r1']
    assert client.put('/context/' + sid, json=data).json()['warnings'] == []
    sid = client.post('/context', json=CTX).json()['sid']
    assert client.put('/context/' + sid, json=data).json()['warnings'] == []


def test_legacy_metrics_normalized_for_warnings(client):
    sid = client.post('/context', json=CTX).json()['sid']
    update_session(sid, {'projectContext': deepcopy(CTX), 'keywordRounds': {'1': {'status': 'done'}}})
    response = client.put('/context/' + sid, json=deepcopy(CTX) | {'keyMetrics': [{'name': '만족'}]})
    assert response.status_code == 200
    assert response.json()['warnings'] == []


def test_invalid_old_context_warning_falls_back(client):
    sid = client.post('/context', json=CTX).json()['sid']
    # Simulate malformed historical data at the warning boundary; avoid asking
    # the store renderer to render an invalid context.
    from app.routers.context import _save_context
    from app.context.models import ProjectContext
    old = load_session(sid)
    old['projectContext'] = deepcopy(CTX) | {'taskMode': 'unknown'}
    old['projectContext']['researchQuestion']['template'] = None
    old['keywordRounds'] = {'1': {'status': 'done'}}
    assert _save_context(sid, ProjectContext(**CTX), old)['warnings'] == ['taskMode_changed_after_r1', 'keyMetrics_changed_after_r1']
