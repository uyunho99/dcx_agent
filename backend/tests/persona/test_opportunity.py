import copy
import json
import math

import pytest

from app.persona.opportunity import baselines, build_map, star, zone
from app.persona.package import Package
from tests.fixtures.evidence_package import make_package


def test_baselines():
    assert baselines([(.1, .2), (.3, .4)]) == {
        's_line': .5, 'diag1': ((0, .30000000000000004), (1, 1)),
        'diag2': ((.2, 0), (1, 1)),
    }


@pytest.mark.parametrize('i,s,expected', [
    (.05, .85, 'A'), (.65, .55, 'B'), (.98, .6, 'C'),
    (0, .35, 'D'), (.3, .2, 'E'), (.95, .05, 'F'),
])
def test_zone_table(i, s, expected):
    assert zone(i, s, baselines([(.4, .25)])) == expected


@pytest.mark.parametrize('i,s,expected', [
    (0, .5, 'A'), (.5, .5, 'B'), (.9, .5, 'C'),
    (0, .25, 'D'), (.5, .625, 'A'),  # diagonal 1 belongs to Overserved
    (.4375, .25, 'E'), (.625, .5, 'B'),  # diagonal 2 belongs to Well-served
    (1, 1, 'A'),
])
def test_boundary_goes_upper(i, s, expected):
    assert zone(i, s, baselines([(.25, .25)])) == expected


def test_points_immediately_below_lines():
    base = baselines([(.25, .25)])
    assert zone(.5, math.nextafter(.5, 0), base) == 'E'
    assert zone(.5, math.nextafter(.625, 0), base) == 'B'
    assert zone(.625, math.nextafter(.5, 0), base) == 'F'


@pytest.mark.parametrize('point,expected', [((1, 0), 'E'), ((1, 1), 'A'), ((0, 0), 'D')])
def test_degenerate_baselines(point, expected):
    assert zone(*point, baselines([point])) == expected


@pytest.mark.parametrize('novelties,odi,expected', [
    (['high', 'very_high'], 1, True),
    (['high', 'high'], 1.1, True),
    (['very_high', 'very_high'], 1, True),
    (['high'], 1.1, False),
    (['high', 'low'], 1.1, False),
    (['high', 'very_high'], .99, False),
    ([], 1.1, False),
])
def test_star_rule(novelties, odi, expected):
    context = {'metrics': {'odi': odi}, 'evidence': [{'novelty': n} for n in novelties]}
    assert star(context, 1) is expected


def test_build_map_uses_all_contexts_and_session_means():
    package = Package.model_validate(make_package())
    before = package.model_dump()
    result = build_map(package)
    contexts = [c for b in package.personas for c in b.context_evidence]
    assert len(result['points']) == len(contexts) == 11
    assert {p['zone'] for p in result['points']} == set('ABCDEF')
    assert [p['context_id'] for p in result['points'] if p['star']] == ['CL0-P0-C2', 'CL0-P1-C2']
    assert result['base'] == baselines([(c.metrics.importance, c.metrics.satisfaction) for c in contexts])
    odi_mean = sum(c.metrics.odi for c in contexts) / len(contexts)
    for point, context in zip(result['points'], contexts):
        assert point['context_id'] == context.context_id
        assert (point['i'], point['s'], point['odi']) == (
            context.metrics.importance, context.metrics.satisfaction, context.metrics.odi)
        assert point['star'] == star(context.model_dump(), odi_mean)
    assert package.model_dump() == before
    json.dumps(result)


def test_shapes_and_tones():
    raw = make_package(personas=9, contexts=(2,) * 9)
    # Four Personas in one cluster, then five more clusters, in package order.
    for index, block in enumerate(raw['personas']):
        block['persona_evidence']['cluster_id'] = f'CL{max(0, index - 3)}'
    result = build_map(Package.model_validate(raw))
    points = result['points'][::2]
    assert [p['shape'] for p in points] == ['circle'] * 4 + [
        'square', 'triangle', 'diamond', 'pentagon', 'circle']
    assert [p['tone'] for p in points[:4]] == ['--ink-strong', '--ink', '--line-strong', '--ink-strong']
    assert all(p['tone'] == '--ink-strong' for p in points[4:])
    assert [p['cluster_label'] for p in points] == [None] * 8 + ['CL5']
    for first, second in zip(result['points'][::2], result['points'][1::2]):
        assert (first['shape'], first['tone']) == (second['shape'], second['tone'])
    assert [c['cluster_id'] for c in result['legend']] == [f'CL{i}' for i in range(6)]
    for cluster in result['legend']:
        cluster_points = [p for p in points if p['cluster_id'] == cluster['cluster_id']]
        assert cluster['shape'] == cluster_points[0]['shape']
        assert cluster['cluster_label'] == cluster_points[0]['cluster_label']
        assert [(p['persona_id'], p['tone']) for p in cluster['personas']] == [
            (p['persona_id'], p['tone']) for p in cluster_points]
        assert all(p['persona_name'] for p in cluster['personas'])


def test_counter_hollow():
    result = build_map(Package.model_validate(make_package()))
    assert [p['context_id'] for p in result['points'] if p['counter']] == ['CL0-P1-C0']
    assert all(p['hollow'] is p['counter'] for p in result['points'])


def test_empty_map_and_overlapping_points():
    raw = make_package()
    raw['personas'] = []
    assert build_map(Package.model_validate(raw)) == {
        'points': [], 'base': baselines([]), 'legend': []}
    assert baselines([]) == {'s_line': .5, 'diag1': ((0, .5), (1, 1)), 'diag2': ((.5, 0), (1, 1))}
    raw = make_package()
    metrics = raw['personas'][0]['context_evidence'][0]['metrics']
    raw['personas'][0]['context_evidence'][1]['metrics'] = copy.deepcopy(metrics)
    points = build_map(Package.model_validate(raw))['points']
    assert len(points) == 11
    assert points[0]['context_id'] != points[1]['context_id']
    assert (points[0]['i'], points[0]['s']) == (points[1]['i'], points[1]['s'])
