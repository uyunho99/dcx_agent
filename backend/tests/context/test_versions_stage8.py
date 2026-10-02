import pytest

from app.context import store, versions
from app.persona.store import PersonaStore
from app.routers.sessions import _completion


@pytest.fixture
def completed(data_dir):
    from tests.fixtures.evidence_package import write_session_with_package
    from app.persona.package import load_package
    sid = write_session_with_package(data_dir).sid
    package = load_package(sid, 'v1')
    store.update_session(sid, dict(schemaVersion=2, segment={'status': 'done'},
        evidence={'status': 'done'}, persona={'status': 'done'}, insight={'status': 'done'},
        completion=dict(segmentDone=True, personaDone=True, insightDone=True)))
    root = versions.version_dir(sid, 'v1')
    for name in ('segment', 'evidence'):
        store.write_json(root / name / 'keep.json', {'keep': True})
    persona = PersonaStore.open(sid, 'v1')
    persona.write('cards', {'run': 'r1', 'package_run': package.run, 'personas': {'P1': {'status': 'done', 'card': {'persona_name': 'name'}}}})
    persona.write('stage_8', {'cards': 1, 'failed': 0, 'grades': {'observed': 2}, 'llm_calls': {'card': 1}})
    persona.new_revision('insights', [{'id': 'I1'}], by='derive', message=None)
    return sid


@pytest.mark.parametrize('stage', [6, 7, 8])
def test_restart_stage8_artifacts_and_completion(completed, stage):
    versions.create_version(completed, 'v1', f'stage{stage}', '')
    root = versions.version_dir(completed, 'v2')
    assert not (root / 'persona').exists()
    assert (root / 'segment/keep.json').exists() == (stage > 6)
    assert (root / 'evidence/keep.json').exists() == (stage > 7)
    data = store.read_json(root / 'session.json')
    assert not {'personaDone', 'insightDone'} & data['completion'].keys()
    assert data['persona']['status'] == data['insight']['status'] == 'stale'
    assert (versions.version_dir(completed, 'v1') / 'persona/cards.json').exists()


def test_compare_stage8_summary(completed):
    versions.create_version(completed, 'v1', 'stage9', '')
    assert versions.compare(completed, 'v1', 'v2', 'stage8')['same']
    persona = PersonaStore.open(completed, 'v2')
    report = persona.read('stage_8')
    report['failed'] = 1
    persona.write('stage_8', report)
    diff = versions.compare(completed, 'v1', 'v2', 'stage8')
    assert not diff['same']
    assert diff['before']['report']['cards'] == 1
    assert diff['after']['report']['failed'] == 1
    assert diff['after']['insights']['revision'] == 1
    persona.write('cards', {'run': 'r2', 'personas': {}})
    assert not versions.compare(completed, 'v1', 'v2', 'stage8')['same']
    versions.create_version(completed, 'v2', 'stage8', '')
    assert versions.compare(completed, 'v2', 'v3', 'stage8')['after']['report'] is None
    assert not (versions.version_dir(completed, 'v3') / 'persona').exists()


def test_completion_uses_selected_version_and_durable_insights(completed):
    data = store.read_json(versions.version_dir(completed, 'v1') / 'session.json')
    assert _completion(completed, data, 'v1')['personaDone']
    assert _completion(completed, data, 'v1')['insightDone']
    data['stale'] = {'stage8': 'changed'}
    assert not _completion(completed, data, 'v1')['personaDone']
    assert not _completion(completed, data, 'v1')['insightDone']
    versions.create_version(completed, 'v1', 'stage8', '')
    assert _completion(completed, {**data, 'stale': {}}, 'v1')['insightDone']
    assert not _completion(completed, {**data, 'stale': {}}, 'v2')['insightDone']
