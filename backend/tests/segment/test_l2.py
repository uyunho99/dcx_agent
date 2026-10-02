"""Offline contracts for noun-network Personas and the quality callback."""
from itertools import permutations

import networkx as nx
import numpy as np
import pytest

from app.segment import l2, params, quality
from app.segment.inputs import load_input
from tests.fixtures.segment_synth import PERSONAS, make_segment_session


def corpus(sizes, words=4):
    return {f'{p}-{d}': [f'p{p}-{w:03d}' for w in range(words)]
            for p, size in enumerate(sizes) for d in range(size)}


def fixed_partition(monkeypatch, groups):
    monkeypatch.setattr(nx.community, 'louvain_communities',
                        lambda graph, **kwargs: [set(g) for g in groups])


def test_communities_match_personas(data_dir):
    synth = make_segment_session(data_dir)
    source = load_input(synth.sid, synth.version)
    expected = synth.expected['assignments']
    for c, count in enumerate(PERSONAS):
        ids = [d for d in source.ids if expected[d]['cluster'] == f'CL{c}']
        result = l2.personas(ids, source.nouns, '에어컨')
        assert len(result.communities) == count
        truth = [int(expected[d]['persona'].split('-P')[1]) for d in ids]
        accuracy = max(sum(mapping[result.assign[d]] == p for d, p in zip(ids, truth))
                       / len(ids) for mapping in permutations(range(count)))
        assert accuracy >= .9


def test_merge_when_more_than_three(monkeypatch):
    nouns = corpus([2, 5, 8, 11, 14])
    groups = [set(nouns[f'{p}-0']) for p in range(5)]
    # Smallest p0 has total weight 2 to p1, versus 3 to p4 (two edges).
    nouns['bridge-a'] = ['p0-000', 'p1-000']
    nouns['bridge-b'] = ['p0-000', 'p1-000']
    nouns['bridge-c'] = ['p0-000', 'p4-000', 'p4-001']
    nouns['bridge-d'] = ['p0-000', 'p4-000']
    for i in range(4):
        nouns[f'bridge-next-{i}'] = ['p1-001', 'p2-001']
    fixed_partition(monkeypatch, groups)
    result = l2.personas(list(nouns), nouns, '')
    assert len(result.communities) == 3
    assert any(groups[0] | groups[4] <= set(g) for g in result.communities)
    assert not any(groups[0] | groups[1] <= set(g) for g in result.communities)


@pytest.mark.parametrize('split_at', [None, 1.5])
def test_resolution_raise_when_one(monkeypatch, split_at):
    nouns = corpus([10, 10])
    calls = []

    def partition(graph, *, resolution, seed, weight):
        calls.append(resolution)
        assert seed == params.SEED and weight == 'weight'
        if resolution == split_at:
            return [set(nouns['0-0']), set(nouns['1-0'])]
        return [set(graph)]

    monkeypatch.setattr(nx.community, 'louvain_communities', partition)
    result = l2.personas(list(nouns), nouns, '')
    assert calls == ([1., 1.2, 1.5] if split_at else [1., 1.2, 1.5, 2.])
    assert result.flags == ([] if split_at else ['few_communities'])


def test_fallback_assignment():
    nouns = corpus([3, 9])
    nouns.update(empty=[], product=['브랜드'])
    ids = ['missing', *nouns]
    result = l2.personas(ids, nouns, '브랜드')
    largest = result.assign['1-0']
    assert all(result.assign[d] == largest for d in ('empty', 'product', 'missing'))
    assert result.fallback_ratio == pytest.approx(3 / 15)
    assert result.assignment_reasons['empty'] == 'fallback'


def test_centrality_top16_normalized():
    nouns = corpus([10, 10], words=25)
    for words in nouns.values():
        words.extend(['브랜드'] * 30)
    result = l2.personas(list(nouns), nouns, '브랜드')
    for scores in result.centrality:
        assert len(scores) == 16
        assert max(s for _, s in scores) == 1.
        assert all(0 < s <= 1 and w != '브랜드' for w, s in scores)
    assert '브랜드' not in set().union(*map(set, result.communities))


def test_network_view_limit():
    nouns = corpus([10, 10, 10], words=30)
    result = l2.personas(list(nouns), nouns, '')
    assert sum(map(len, result.communities)) == 90
    assert len(result.network['nodes']) == 60
    shown = {n['id'] for n in result.network['nodes']}
    assert all(e['source'] in shown and e['target'] in shown for e in result.network['edges'])


def test_empty_graph_single_persona():
    # 1 / 201 falls below .005; repeated tokens must not inflate edge weight.
    nouns = {str(i): [] for i in range(201)}
    nouns['0'] = ['aa', 'bb'] * 100
    result = l2.personas(list(nouns), nouns, '')
    assert len(result.communities) == 1
    assert set(result.assign.values()) == {0}
    assert result.flags == ['few_communities']
    assert result.network['edges'] == []


def test_isolated_community_merges_into_largest_document_community(monkeypatch):
    nouns = corpus([2, 3, 4, 20, 5])
    groups = [set(nouns[f'{p}-0']) for p in range(5)]
    # A large vocabulary is not a large document community.
    nouns['4-0'] += [f'extra-{i}' for i in range(10)]
    groups[4].update(nouns['4-0'])
    fixed_partition(monkeypatch, groups)
    result = l2.personas(list(nouns), nouns, '')
    assert len(result.communities) == 3
    assert any(groups[0] | groups[1] | groups[3] <= set(g) for g in result.communities)
    assert result.fallback_ratio == 0


def test_assignment_uses_all_centralities_and_noun_presence(monkeypatch):
    nouns = corpus([10, 10], words=20)
    groups = [set(nouns[f'{p}-0']) for p in range(2)]
    fixed_partition(monkeypatch, groups)
    # The two p0 words are outside the displayed top 16; duplicates count once.
    nouns['mixed'] = ['p0-018', 'p0-019'] + ['p1-000'] * 100
    result = l2.personas(list(nouns), nouns, '')
    assert result.assign['mixed'] == result.assign['0-0']
    assert result.assignment_reasons['mixed'] == 'centrality'


def test_document_frequency_vocab_cap_and_edge_threshold(monkeypatch):
    nouns = {str(i): ['common', 'partner'] for i in range(200)}
    nouns['0'] += [f'z{i:03d}' for i in range(310)] + ['rare'] * 1000
    observed = []

    def partition(graph, **kwargs):
        observed.append(graph.copy())
        return [set(graph)]

    monkeypatch.setattr(nx.community, 'louvain_communities', partition)
    l2.personas(list(nouns), nouns, 'rare')
    graph = observed[0]
    assert len(graph) == 300
    assert 'common' in graph and 'partner' in graph and 'z309' not in graph
    assert 'rare' not in graph
    assert graph['common']['partner']['weight'] == 200
    assert graph['common']['z000']['weight'] == 1  # exactly .005 is retained


@pytest.mark.parametrize('nouns', [{}, {'a': []}, {'a': ['one']}, {'a': ['one', 'two']}])
def test_empty_and_tiny_inputs(nouns):
    result = l2.personas(list(nouns), nouns, '')
    assert set(result.assign) == set(nouns)
    assert result.flags == (['few_communities'] if len(result.communities) == 1 else [])
    assert np.isfinite(result.fallback_ratio)
    assert all(np.isfinite(s) for scores in result.centrality for _, s in scores)


def test_eigenvector_values_and_weighted_assignment(monkeypatch):
    nouns = {f'{p}-{leaf}-{d}': [f'{p}-hub', f'{p}-leaf{leaf:02d}']
             for p in range(2) for leaf in range(16) for d in range(10)}
    groups = [{f'{p}-hub', *(f'{p}-leaf{i:02d}' for i in range(16))} for p in range(2)]
    fixed_partition(monkeypatch, groups)
    result = l2.personas(list(nouns), nouns, '')
    for scores in result.centrality:
        assert scores[0][0].endswith('hub') and scores[0][1] == 1.
        assert all(score == pytest.approx(.25) for _, score in scores[1:])
    nouns['mixed'] = ['0-hub', '1-leaf00', '1-leaf01']
    result = l2.personas(list(nouns), nouns, '')
    assert result.assign['mixed'] == result.assign['0-0-0']


def test_deterministic_and_quality_ari_callable():
    nouns = corpus([30, 50], words=18)
    ids = list(nouns)
    result = l2.personas(ids, nouns, '')
    assert result == l2.personas(ids, nouns, '')
    reversed_nouns = {d: list(reversed(nouns[d])) for d in reversed(ids)}
    assert result == l2.personas(list(reversed(ids)), reversed_nouns, '')

    def recluster(indices, rng):
        sampled_ids = [ids[int(i)] for i in indices]
        sampled = l2.personas(sampled_ids, nouns, '')
        return [sampled.assign[d] for d in sampled_ids]

    score = quality.resample_ari(np.zeros((len(ids), 1)),
                                [result.assign[d] for d in ids],
                                level='L2', recluster=recluster)
    assert score == pytest.approx(1.)


@pytest.fixture
def rare_noun_corpus():
    nouns = {f'{p}-{d}': [f'{p}{i}' for i in range(8)]
             for p, size in [('a', 40), ('b', 30)] for d in range(size)}
    for p in ('a', 'b'):
        for i in range(7):
            for d in range(3):
                nouns[f'{p}-spoke-{i}-{d}'] = [f'{p}6', f'{p}{i if i < 6 else 7}']
    nouns.update({f'rare-{i}': [f'zz{i:02d}'] for i in range(60)})
    return nouns


def test_rare_isolated_nouns_do_not_displace_hub(rare_noun_corpus):
    result = l2.personas(list(rare_noun_corpus), rare_noun_corpus, '')
    scores = result.centrality[result.assign['a-0']]
    assert ('a6', 1.) in scores
    assert not any(word.startswith('zz') for word, _ in scores)
    assert not any(word.startswith('zz') for group in result.communities for word in group)
    assert not any(node['id'].startswith('zz') for node in result.network['nodes'])
    assert all(result.assignment_reasons[f'rare-{i}'] == 'fallback' for i in range(60))
    assert result.fallback_ratio == pytest.approx(60 / len(rare_noun_corpus))


def test_rare_isolated_nouns_do_not_create_junk_persona(rare_noun_corpus):
    result = l2.personas(list(rare_noun_corpus), rare_noun_corpus, '')
    assert len(result.communities) == 2
    assert result.assign['a-0'] != result.assign['b-0']
    assert all(any(result.assign[d] == i and reason == 'centrality'
                   for d, reason in result.assignment_reasons.items())
               for i in range(len(result.communities)))


def test_merged_components_scale_by_relative_edge_weight():
    graph = nx.Graph()
    graph.add_weighted_edges_from([('hub', f'leaf{i}', 10) for i in range(4)])
    graph.add_edge('small-a', 'small-b', weight=2)
    graph.add_node('isolated')
    scores = l2._centrality(graph)
    assert scores['hub'] == 1.
    assert scores['leaf0'] == pytest.approx(.5)
    assert scores['small-a'] == scores['small-b'] == pytest.approx(2 / 40)
    assert scores['isolated'] == 0.


@pytest.mark.parametrize('group_count', [2, 4])
def test_zero_document_communities_dropped_before_persona_range(monkeypatch, group_count):
    nouns = {str(i): [f'w{j}' for j in range(group_count * 2)] for i in range(10)}
    calls = []

    def partition(graph, *, resolution, **kwargs):
        calls.append(resolution)
        return [{f'w{2 * i}', f'w{2 * i + 1}'} for i in range(group_count)]

    monkeypatch.setattr(nx.community, 'louvain_communities', partition)
    result = l2.personas(list(nouns), nouns, '')
    assert calls == list(params.L2_RESOLUTIONS)
    assert result.communities == [['w0', 'w1']]
    assert set(result.assign.values()) == {0}
    assert result.flags == ['few_communities']
    assert result.fallback_ratio == 0
