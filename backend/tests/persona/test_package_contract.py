"""D-301: real offline stage-seven output is the stage-eight contract."""
from collections import defaultdict
from copy import deepcopy

import pytest

from app.context import store as sessions
from app.context.versions import version_dir
from app.evidence.package import EvidencePackage
from app.llm.fake import FakeBackend
from app.llm import registry
from app.persona.cards import generate_card
from app.persona.concepts import _hydrate
from app.persona.insights import opportunity_bars
from app.persona.opportunity import build_map
from app.persona.package import PackageInvalid, evidence_index, load_package
from tests.evidence.test_integration import offline_worker, bind_backend, run_and_poll
from tests.fixtures.evidence_package import make_package
from tests.fixtures.evidence_synth import make_evidence_session


def object_keys(value):
    """Check every object, including every list element, by structural path."""
    found = defaultdict(set)

    def visit(item, path):
        if isinstance(item, dict):
            found[path].add(frozenset(item))
            for key, child in item.items():
                visit(child, (*path, key))
        elif isinstance(item, list):
            for child in item:
                visit(child, (*path, '[]'))
    visit(value, ())
    return dict(found)


def test_real_stage7_package_loads_and_generates_cards(client, data_dir, monkeypatch, offline_worker):
    fixture = make_evidence_session(data_dir, clusters=3, personas=(1, 1, 1),
                                    contexts=(2, 2, 2), docs_per_context=12)
    bind_backend(monkeypatch, fixture)
    original = registry.run_task

    def varied_tags(task):
        result = original(task)
        if task.task == 'evidence.tag' and result.ok:
            for item in result.data.items:
                item.polarity = -1.0 if int(item.doc_id[1:]) % 3 == 0 else 1.0
                item.artifacts = ['리모컨']
        return result

    monkeypatch.setattr(registry, 'run_task', varied_tags)
    run_and_poll(client, fixture)
    path = version_dir(fixture.sid, fixture.version) / 'evidence/package.json'
    real = sessions.read_json(path)
    synthetic = make_package()
    EvidencePackage.model_validate(synthetic)
    assert object_keys(synthetic) == object_keys(real)
    package = load_package(fixture.sid, fixture.version)
    backend = FakeBackend()
    for block in package.personas:
        result = generate_card(fixture.sid, block, run_task=backend.run)
        assert result.status == 'done', result.error
    assert build_map(package)['points']

    # Pass the real producer output through both HTTP launches and worker dispatch.
    import time
    from app.work import runner
    monkeypatch.setattr(registry, 'run_task', backend.run)
    for kind, body in [('persona', {}), ('insight', {'mode': 'derive'})]:
        response = client.post(f'/{kind}/{fixture.sid}/run', json=body)
        assert response.status_code == 200, response.text
        run_id = response.json()['runId']
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            work = next(row for row in runner.status(fixture.sid) if row['runId'] == run_id)
            if work['state'] not in ('running', 'paused'):
                break
            time.sleep(.01)
        assert work['state'] == 'done', work
    assert client.get(f'/insight/{fixture.sid}').json()['insights']['items']
    saved = sessions.load_session(fixture.sid)
    sessions.update_session(fixture.sid, {'evidence': {**saved['evidence'], 'status': 'running'}})
    assert client.post(f'/persona/{fixture.sid}/run', json={}).status_code == 409
    sessions.update_session(fixture.sid, {'evidence': saved['evidence']})

    # A generation change can have identical package contents (e.g. cached rerun).
    from app.persona import pipeline
    from app.persona.store import PersonaStore
    PersonaStore.open(fixture.sid, fixture.version).write('cards', {
        'package_run': package.run, 'package_hash': pipeline._digest(package)})
    from app.routers.sessions import _completion
    sessions.update_session(fixture.sid, {'persona': {'status': 'done'}})
    assert _completion(fixture.sid, sessions.load_session(fixture.sid), fixture.version)['personaDone']
    sessions.update_session(fixture.sid, {'evidence': {'status': 'done', 'run': 'next-run'}})
    assert not _completion(fixture.sid, sessions.load_session(fixture.sid), fixture.version)['personaDone']
    assert pipeline.mark_stale_if_changed(fixture.sid, fixture.version)

    # Valid all-tab / unquoted evidence and absent metrics must remain absent.
    nullable = deepcopy(real)
    block = nullable['personas'][0]
    context = block['context_evidence'][0]
    item = context['evidence'][0]
    item.update(quote=None, novelty=None, polarity=None, tab=['all'])
    for key in ('importance', 'satisfaction', 'odi'):
        context['metrics'][key] = None
    for key in context['metrics']['quality']:
        context['metrics']['quality'][key] = None
    sessions.write_json(path, nullable)
    package = load_package(fixture.sid, fixture.version)
    block = package.personas[0]
    result = generate_card(fixture.sid, block, run_task=backend.run)
    assert result.status == 'done', result.error
    refs = evidence_index(block)
    number, ref = next((n, r) for n, r in refs.items() if r.quote is None)
    assert ref.verified is False and ref.field is None
    concept = _hydrate({'pain_points': [number], 'journey': [], 'persona_profile': 'test'},
                       'I1', 'basis', refs, {number: block.persona_evidence.persona_id})
    assert concept['pain_points'][0]['quote'] is None
    point = build_map(package)['points'][0]
    assert point['i'] is point['s'] is point['odi'] is point['zone'] is None
    assert not point['star']
    assert opportunity_bars([{'id': 'I1', 'context_ids': ['C1']}], {'C1': None}) == {
        'bars': [{'id': 'I1', 'odi': None}], 'mean': None, 'targets': []}

    # The producer's model, not just a permissive local projection, validates loads.
    nullable['schema'] = 'unsupported'
    sessions.write_json(path, nullable)
    with pytest.raises(PackageInvalid):
        load_package(fixture.sid, fixture.version)
