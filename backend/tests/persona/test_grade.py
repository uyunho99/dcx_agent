from copy import deepcopy

import pytest

from app.persona.grade import grade_card, grade_field, traceable_support
from app.persona.package import Package, evidence_index
from tests.fixtures.evidence_package import make_package


@pytest.fixture
def refs():
    return evidence_index(Package.model_validate(make_package()).personas[0])


def cell(cites=(), text='내용'):
    return {'text': text, 'cite': list(cites)}


@pytest.mark.parametrize('field,cites,expected', [
    ('state', ['E2'], 'observed'),
    ('state', ['E7'], 'inferred'),
    ('barrier', ['E2'], 'observed'),
    ('usage_context', ['E2'], 'observed'),
    ('emotion', ['E2'], 'inferred'),
    ('jtbd', ['E2'], 'inferred'),
    ('unmet_need', ['E2'], 'inferred'),
    ('barrier', [], 'speculated'),
    ('state', ['E99'], 'speculated'),
    ('state', ['E2', 'E99'], 'speculated'),
    ('state', ['E7', 'E2'], 'observed'),
    ('intent', ['E2'], 'speculated'),
    ('intent', [], 'speculated'),
    ('persona_profile', ['E2'], 'speculated'),
    ('persona_profile', [], 'speculated'),
    ('unknown', ['E2'], 'speculated'),
])
def test_grade_table(refs, field, cites, expected):
    assert grade_field(field, cites, refs) == expected


@pytest.mark.parametrize('fields,expected', [
    ({}, 0.0),
    ({'state': None, 'emotion': cell(['E2'], None)}, 0.0),
    ({'state': cell(['E2']), 'emotion': None}, 1.0),
    ({'state': cell(['E7'])}, 1.0),
    ({'state': cell(['E2', 'E2']), 'emotion': cell()}, 0.5),
    ({'state': cell(['E2', 'E99'])}, 0.0),
    ({'state': cell(['E99'])}, 0.0),
])
def test_support_counts_populated_fields_with_valid_citations(refs, fields, expected):
    assert traceable_support(fields, refs) == expected


def test_downgrade_is_per_context_and_pure(refs):
    fields = dict(state=cell(['E2']), emotion=cell(['E2']), barrier=cell(),
                  usage_context=cell(['E99']), jtbd=cell())
    assert traceable_support(fields, refs) == 0.4
    card = {'contexts': [dict(context_id='CL0-P0-C0', **fields),
                         dict(context_id='CL0-P0-C1', state=cell(['E6']), emotion=cell())]}
    original, original_refs = deepcopy(card), deepcopy(refs)
    result = grade_card(card, refs)
    assert result['grades']['CL0-P0-C0'] == dict(state='inferred', emotion='speculated',
        barrier='speculated', usage_context='speculated', jtbd='speculated')
    assert result['grades']['CL0-P0-C1'] == dict(state='observed', emotion='speculated')
    assert result['traceable_support'] == {'CL0-P0-C0': 0.4, 'CL0-P0-C1': 0.5}
    assert card == original and refs == original_refs
    assert grade_card(card, refs) == result


def test_null_cells_have_no_grade_or_trace(refs):
    card = {'contexts': [dict(context_id='CL0-P0-C0', state=cell(['E2']),
                              emotion=None, barrier=cell(['E2'], None))]}
    result = grade_card(card, refs)
    assert result['grades']['CL0-P0-C0'] == {'state': 'observed'}
    assert result['traceable_support']['CL0-P0-C0'] == 1.0
    assert [row['field'] for row in result['trace']] == ['state']


def test_trace_preserves_package_provenance_and_deduplicates(refs):
    card = {'contexts': [dict(context_id='CL0-P0-C0', state=cell(['E2', 'E2', 'E4', 'E5', 'E99']))]}
    result = grade_card(card, refs)
    assert result['grades']['CL0-P0-C0']['state'] == 'speculated'
    assert [row['evidence_id'] for row in result['trace']] == ['E2', 'E4', 'E5']
    for row in result['trace']:
        assert row['context_id'] == 'CL0-P0-C0'
        assert row['field'] == 'state'
        assert row['evidence'] == refs[row['evidence_id']].model_dump()
    result['trace'][0]['evidence']['quote']['text'] = 'changed'
    assert refs['E2'].quote.text != 'changed'


def test_summary_and_synthetic_profile(refs):
    card = dict(contexts=[], intent=cell(['E2']), persona_profile='합성 프로필',
                usage_context=cell(['E1']), jtbd=cell(['E1']), values=None)
    result = grade_card(card, refs)
    assert result['summary'] == dict(intent='speculated', persona_profile='speculated',
                                     usage_context='observed', jtbd='inferred')
    assert result['grades'] == {}
    assert result['traceable_support'] == {}
