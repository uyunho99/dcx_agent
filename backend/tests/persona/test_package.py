import copy
import json

import pytest
from pydantic import ValidationError

from app.persona.package import Package, PackageMissing, evidence_index, load_package
from app.segment.store import SegmentStore
from tests.fixtures.evidence_package import make_package, write_session_with_package, fake_persona_backend


def contexts(package):
    return [c for p in package['personas'] for c in p['context_evidence']]


@pytest.mark.parametrize('big', [None, 10])
def test_fixture_has_all_zones(big):
    rows = contexts(make_package(big_persona_contexts=big))
    im = sum(c['metrics']['importance'] for c in rows) / len(rows)
    sm = sum(c['metrics']['satisfaction'] for c in rows) / len(rows)
    zones = set()
    for c in rows:
        i, s = (c['metrics'][key] for key in ('importance', 'satisfaction'))
        column = 0 if s >= sm + (1-sm)*i else 2 if s < (i-im)/(1-im) else 1
        zones.add(('ABC' if s >= .5 else 'DEF')[column])
    assert zones == set('ABCDEF')


def test_fixture_star_two():
    rows = contexts(make_package())
    mean = sum(c['metrics']['odi'] for c in rows) / len(rows)
    assert sum(sum(e['novelty'] in ('high', 'very_high') for e in c['evidence']) >= 2
               and c['metrics']['odi'] >= mean for c in rows) == 2


def test_fixture_counter_and_unverified():
    package = make_package()
    assert sum('counter_context' in c['flags'] for c in contexts(package)) == 1
    refs = [r for b in Package.model_validate(package).personas for r in evidence_index(b).values()]
    assert any(not r.verified for r in refs)
    assert {'support', 'counter', 'rare'} <= {r.role for r in refs}


def test_fixture_zero_evidence_context():
    assert sum(not any(c[k] for k in ('evidence', 'counter_evidence', 'rare_evidence'))
               for c in contexts(make_package())) == 1


def test_big_persona_ten_contexts():
    package = make_package(big_persona_contexts=10)
    assert [len(p['context_evidence']) for p in package['personas']] == [10, 3, 3, 2]
    assert make_package(seed=73) == make_package(seed=73)


def test_load_package_validates_required(data_dir):
    path = data_dir / 'sessions/test/versions/v1/evidence/package.json'
    path.parent.mkdir(parents=True)
    data = make_package()
    data['future'] = {'anything': True}
    data['personas'][0]['context_evidence'][0]['future'] = 1
    path.write_text(json.dumps(data))
    assert load_package('test', 'v1').model_dump(by_alias=True)['future'] == {'anything': True}
    for route in [('schema',), ('params',), ('personas', 0, 'persona_evidence', 'goal'),
                  ('personas', 0, 'context_evidence', 0, 'context_id'),
                  ('personas', 0, 'context_evidence', 0, 'metrics', 'odi'),
                  ('personas', 0, 'context_evidence', 0, 'evidence', 0, 'quote', 'text')]:
        broken = copy.deepcopy(data)
        parent = broken
        for key in route[:-1]:
            parent = parent[key]
        del parent[route[-1]]
        path.write_text(json.dumps(broken))
        with pytest.raises(ValidationError):
            load_package('test', 'v1')
    path.write_text('{broken')
    with pytest.raises(ValidationError):
        load_package('test', 'v1')
    with pytest.raises(PackageMissing):
        load_package('test', 'v2')


def test_evidence_index_renumbers_persona_wide():
    block = Package.model_validate(make_package()).personas[0]
    refs = evidence_index(block)
    expected = [(None, 'support', e) for e in block.persona_evidence.desire_support]
    for c in block.context_evidence:
        expected.extend((c.context_id, role, e) for key, role in
                        [('evidence', 'support'), ('counter_evidence', 'counter'), ('rare_evidence', 'rare')]
                        for e in getattr(c, key))
    assert list(refs) == [f'E{i}' for i in range(1, len(expected)+1)]
    for ref, (cid, role, ev) in zip(refs.values(), expected):
        assert (ref.context_id, ref.role, ref.doc_id, ref.field) == (cid, role, ev.doc_id, ev.quote.field)
        assert (ref.verified, ref.novelty, ref.quote) == (ev.quote.verified, ev.novelty, ev.quote)
    assert refs == evidence_index(block)


def test_session_package_matches_confirmed_segment(data_dir):
    session = write_session_with_package(data_dir, big_persona_contexts=10)
    package = load_package(session.sid, session.version)
    store = SegmentStore.open(session.sid, session.version)
    ps = {p['persona_id']: p for p in store.personas()}
    cs = {c['context_id']: c for c in store.contexts()}
    assert len(ps) == len(package.personas) == 4
    for block in package.personas:
        p = block.persona_evidence
        confirmed = ps[p.persona_id]
        assert confirmed['confirmed_at']
        assert (p.persona_name, p.desire, p.goal) == (confirmed['name'], confirmed['desire'], confirmed['goals'])
        for c in block.context_evidence:
            assert cs[c.context_id]['confirmed_at']
            assert (c.context_name, c.action) == (cs[c.context_id]['name'], cs[c.context_id]['action'])
            assert cs[c.context_id]['persona_id'] == p.persona_id
    data = json.loads((data_dir / 'sessions' / session.sid / 'versions/v1/session.json').read_text())
    assert '의료적 효과 표현 금지' in data['projectContext']['constraints']
    assert data['segment']['status'] == 'done'


def test_fake_responses_use_actual_references():
    package = make_package(big_persona_contexts=10, seed=17)
    backend = fake_persona_backend(package)
    names = ('persona.card', 'persona.summary', 'persona.prescribe', 'persona.constraint_check',
             'persona.scope', 'insight.derive', 'insight.concept', 'insight.edit')
    assert set(backend.responses) == set(names)
    card = json.loads(backend.responses['persona.card'])
    block = Package.model_validate(package).personas[0]
    refs = evidence_index(block)
    assert {c['context_id'] for c in card['contexts']} == {c.context_id for c in block.context_evidence}
    for c in card['contexts']:
        for field in ('state', 'emotion', 'barrier'):
            assert all(refs[e].context_id == c['context_id'] for e in c[field]['cite'])
    all_ids = {c['context_id'] for c in contexts(package)}
    for task in ('insight.derive', 'insight.edit'):
        items = json.loads(backend.responses[task])['items']
        assert 3 <= len(items) <= 8
        assert all(set(i['context_ids']) <= all_ids for i in items)
    concept = json.loads(backend.responses['insight.concept'])
    assert len(concept['pain_points']) == 3
    assert set(concept['pain_points']) <= refs.keys()
    assert all(r['context_id'] in all_ids for r in concept['journey'])
    assert json.loads(backend.responses['persona.constraint_check'])['constraints'][0]['verdict'] == 'violates'
    for task in names:
        assert json.loads((backend.fixture_dir / f'{task}.json').read_text()) == json.loads(fake_persona_backend(make_package()).responses[task])


def test_fake_backend_selects_persona_chunk_and_empty_fields():
    from app.llm.base import Attachment, LLMTask
    from pydantic import create_model

    package = make_package()
    block = package['personas'][-1]
    payload = {'persona_id': block['persona_evidence']['persona_id'],
               'context_ids': [block['context_evidence'][-1]['context_id']]}
    backend = fake_persona_backend(package)
    schema = create_model('CardResponse', contexts=(list[dict], ...))
    task = LLMTask(task='persona.card', sid='test', instructions='fixture',
                   attachments=[Attachment(title='chunk', body=json.dumps(payload))], output_schema=schema)
    result = backend.run(task)
    assert result.ok
    assert len(result.data.contexts) == 1
    assert result.data.contexts[0]['context_id'] == payload['context_ids'][0]
    for field in ('state', 'emotion', 'barrier'):
        assert result.data.contexts[0][field] == {'text': None, 'cite': []}
    task = task.model_copy(update={'task': 'persona.constraint_check',
                                  'output_schema': create_model('Check', constraints=(list[dict], ...))})
    result = backend.run(task)
    assert result.ok and result.data.constraints[0]['verdict'] == 'ok'


def test_fake_backend_responses_validate_and_concept_edit():
    from app.llm.base import Attachment, LLMTask
    from pydantic import create_model

    backend = fake_persona_backend(make_package())
    fields = {
        'persona.card': {'contexts': list[dict]},
        'persona.summary': dict(intent=dict, usage_context=dict, jtbd=dict, journey=dict,
                                sensitivity=dict, values=str | None, decision_style=str | None),
        'persona.prescribe': dict(direction=str, target_metric=str, contribution=str, journey_hypothesis=str),
        'persona.constraint_check': {'constraints': list[dict]},
        'persona.scope': dict(verdict=str, reason=str),
        'insight.derive': {'items': list[dict]},
        'insight.edit': {'items': list[dict]},
        'insight.concept': dict(persona_profile=str, pain_points=list[str], journey=list[dict], constraint_check=list[dict]),
    }
    for name, required in fields.items():
        task = LLMTask(task=name, sid='test', instructions='fixture', attachments=[],
                       output_schema=create_model('Response', **{k: (v, ...) for k, v in required.items()}))
        result = backend.run(task)
        assert result.ok, (name, result.error)
        if name == 'insight.concept':
            edit = task.model_copy(update={'task': 'insight.edit', 'attachments': [
                Attachment(title='edit', body=json.dumps({'target': 'concept:I1'}))]})
            assert backend.run(edit).ok
    # These values must be supplied by code, never by the fake language model.
    for raw in backend.responses.values():
        assert not any(f'"{key}"' in raw for key in ('odi', 'radar', 'basis', 'quote', 'importance', 'satisfaction'))
