import copy
import json
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import cam
from app.services.s3 import save_json, load_json, list_objects
from app.routers.cam import router


def draft(package):
    columns = []
    for action in package['actions']:
        docs = [e for e in package['evidence'] if e['action_id'] == action['action_id']]
        cell = {'text': docs[0]['quote'], 'grade': 'observed', 'cites': ['invented']}
        columns.append({
            'action_id': action['action_id'], 'context_id': action['context_id'],
            'context': copy.deepcopy(cell), 'action': copy.deepcopy(cell),
            'barrier': None, 'keywords': [], 'artifacts': [],
            'sentiment': None, 'opportunity': None,
            'measurements': [{'doc_id': e['doc_id'], 'importance': 8, 'satisfaction': 5} for e in docs],
        })
    return {'columns': columns}


def generate(monkeypatch, package, response=None, **kwargs):
    llm = Mock(return_value=json.dumps(response or draft(package)))
    monkeypatch.setattr(cam, 'call_claude', llm)
    return cam.describe_cam(package, **kwargs), llm


def test_machine_grades_cites_and_all_rows(monkeypatch, golden_evidence):
    package = golden_evidence()
    original = copy.deepcopy(package)
    result, llm = generate(monkeypatch, package)
    assert package == original
    assert llm.call_count == 1
    assert result['grades'] == {'confirmed': 4, 'inferred': 0, 'speculated': 0, 'ratio_spec': 0}
    for col in result['columns']:
        assert {'context', 'action', 'barrier', 'keywords', 'artifacts', 'sentiment', 'opportunity'} <= col.keys()
        assert col['barrier'] is None and col['barrier_gen_fail'] is True
        assert col['context']['grade'] == 'confirmed'
        assert col['context']['cites']
        scope = {e['doc_id'] for e in package['evidence'] if e['action_id'] == col['action_id']}
        assert set(col['context']['cites']) <= scope
        assert 'invented' not in col['context']['cites']
    assert any(w['code'] == 'LLM_GRADE_IGNORED' for w in result['warnings'])


def test_scoped_retrieval_and_overlap_boundary():
    scope = [{'doc_id': 'd1', 'quote': 'alpha beta'}]
    assert cam.grade_cell({'text': 'alpha beta gamma delta epsilon'}, scope)['grade'] == 'confirmed'
    assert cam.grade_cell({'text': 'alpha gamma delta epsilon'}, scope)['grade'] == 'inferred'
    assert cam.grade_cell({'text': 'unrelated'}, scope) == {'text': 'unrelated', 'grade': 'speculated', 'cites': []}
    assert cam.grade_cell({'text': 'alpha beta'}, [])['grade'] == 'speculated'


def test_speculation_preserved_confidence_lowered(monkeypatch, golden_evidence):
    package = golden_evidence()
    response = draft(package)
    for col in response['columns']:
        col['context']['text'] = '외계인이 순간이동한다'
        col['action']['text'] = '은하수로 텔레포트한다'
    result, _ = generate(monkeypatch, package, response, confidence=0.8)
    assert len(result['columns']) == 2
    assert result['grades']['speculated'] == 4
    assert result['grades']['ratio_spec'] == 1
    assert result['confidence'] < 0.8
    assert result['confidence_before'] == 0.8 and result['confidence_lowered']
    assert result['columns'][0]['context']['text'] == '외계인이 순간이동한다'


def test_other_action_and_centroid_cannot_supply_cites(monkeypatch, golden_evidence):
    package = golden_evidence()
    for index, evidence in enumerate(package['evidence']):
        evidence['quote'] = 'onlyfirst' if evidence['action_id'].endswith('A1') else 'onlysecond'
    response = draft(package)
    response['columns'][0]['context']['text'] = 'onlysecond'
    response['columns'][0]['action']['text'] = package['centroid_sentence']['text']
    result, _ = generate(monkeypatch, package, response)
    assert result['columns'][0]['context']['grade'] == 'speculated'
    assert result['columns'][0]['action']['cites'] == []


@pytest.mark.parametrize('damage', ['json', 'missing_barrier', 'missing_action', 'foreign_measurement', 'duplicate_measurement', 'nan', 'empty_barrier'])
def test_schema_retry_then_stop(monkeypatch, golden_evidence, damage):
    package = golden_evidence()
    response = draft(package)
    col = response['columns'][0]
    if damage == 'missing_barrier':
        del col['barrier']
    elif damage == 'missing_action':
        response['columns'].pop()
    elif damage == 'foreign_measurement':
        col['measurements'][0]['doc_id'] = 'foreign'
    elif damage == 'duplicate_measurement':
        col['measurements'].append(col['measurements'][0])
    elif damage == 'nan':
        col['measurements'][0]['importance'] = float('nan')
    elif damage == 'empty_barrier':
        col['barrier'] = {'text': ''}
    llm = Mock(return_value='broken' if damage == 'json' else json.dumps(response))
    monkeypatch.setattr(cam, 'call_claude', llm)
    with pytest.raises(cam.CamGenerationError):
        cam.describe_cam(package)
    assert llm.call_count == 2


def test_schema_retry_recovers(monkeypatch, golden_evidence):
    package = golden_evidence()
    llm = Mock(side_effect=['broken', json.dumps(draft(package))])
    monkeypatch.setattr(cam, 'call_claude', llm)
    assert cam.describe_cam(package)['columns']
    assert llm.call_count == 2


@pytest.mark.parametrize('session', ['a', 'b'])
@pytest.mark.parametrize('persona_id', ['CL0-P1', 'CL1-P1', 'CL2-P1'])
def test_all_golden_evidence_inputs(monkeypatch, golden_evidence, session, persona_id):
    package = golden_evidence(persona_id, session=session)
    response = draft(package)
    result, _ = generate(monkeypatch, package, response)
    assert result['persona_id'] == persona_id
    assert result['sid'] == package['sid']
    for source, col in zip(response['columns'], result['columns']):
        assert source['measurements'] == col['measurements']


def test_speculation_limit_is_strictly_greater(monkeypatch, golden_evidence):
    package = golden_evidence()
    response = draft(package)
    response['columns'][0]['context']['text'] = '외계인이 순간이동한다'
    result, _ = generate(monkeypatch, package, response, confidence=0.8, speculation_max=0.25)
    assert result['grades']['ratio_spec'] == 0.25
    assert result['confidence'] == 0.8
    assert result['confidence_lowered'] is False


def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_routes_persist_reopen_without_llm(monkeypatch, golden_evidence):
    package = golden_evidence()
    save_json('evidence/golden-a/CL0-P1_20260918_120000.json', package)
    monkeypatch.setattr(cam, 'call_claude', Mock(return_value=json.dumps(draft(package))))
    with client() as api:
        response = api.post('/api/cam/describe', json={'sid': 'golden-a', 'persona_id': 'CL0-P1'})
        assert response.status_code == 200
        monkeypatch.setattr(cam, 'call_claude', Mock(side_effect=AssertionError('must reuse stored CAM')))
        first = api.get('/api/cam/golden-a/CL0-P1')
        assert first.status_code == 200
        assert first.json() == api.get('/api/cam/golden-a/CL0-P1').json()
        assert api.get('/api/cam/status/golden-a/CL0-P1').json()['status'] == 'done'
        assert api.get('/api/cam/golden-a/CL9-P1').status_code == 404


def test_failed_job_records_gen_fail_and_no_cam(monkeypatch, golden_evidence):
    package = golden_evidence()
    save_json('evidence/golden-a/CL0-P1_20260918_120000.json', package)
    llm = Mock(return_value='broken')
    monkeypatch.setattr(cam, 'call_claude', llm)
    cam.run_cam({'sid': 'golden-a', 'persona_id': 'CL0-P1'})
    assert llm.call_count == 2
    assert not list_objects('cam/golden-a/')
    stage = load_json('sessions/golden-a/stage_10.json')
    assert stage['cam_gen_fail'] and stage['persona_id'] == 'CL0-P1'
    assert cam.get_cam_job('golden-a', 'CL0-P1')['status'] == 'error'
