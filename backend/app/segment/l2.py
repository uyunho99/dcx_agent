"""Deterministic, per-cluster noun co-occurrence Personas (D-220)."""
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from math import fsum

import networkx as nx

from app.segment import params


@dataclass
class PersonaResult:
    """Lists are indexed by zero-based, lexically ordered Persona index.

    communities contains the complete noun lists; centrality contains at most
    CENTRALITY_TOP (word, score) pairs per Persona, without padding. network is
    a cluster-wide view: nodes {id, persona, score}, edges {source, target,
    weight}. assignment_reasons records 'centrality' or 'fallback' per doc.
    """

    assign: dict[str, int]
    communities: list[list[str]]
    centrality: list[list[tuple[str, float]]]
    network: dict
    flags: list[str]
    fallback_ratio: float
    assignment_reasons: dict[str, str]


def _centrality(graph):
    """Normalize each connected component to max 1, including merged islands.

    NetworkX rejects disconnected graphs. Component-wise normalization keeps
    isolated merged communities represented rather than giving them zero
    weight. One/two-node components have equal analytical scores; ARPACK's
    sparse solver cannot handle those sizes. Round numerical noise so tied
    nouns, assignments and persisted scores do not depend on ARPACK starts.
    """
    scores = {}
    for component in sorted(nx.connected_components(graph), key=lambda c: tuple(sorted(c))):
        subgraph = graph.subgraph(sorted(component)).copy()
        if len(component) <= 2:
            values = dict.fromkeys(component, 1.)
        else:
            values = nx.eigenvector_centrality_numpy(subgraph, weight='weight')
        maximum = max(values.values())
        scores.update((word, round(value / maximum, 12)) for word, value in values.items())
    return scores


def _ordered(communities):
    return sorted((set(c) for c in communities), key=lambda c: tuple(sorted(c)))


def _assign_profiles(profiles, scores):
    """Score unique noun sets once; count documents before assigning fallbacks."""
    lookup = {word: (index, score) for index, values in enumerate(scores)
              for word, score in values.items()}
    assigned, counts = {}, [0] * len(scores)
    for words, count in profiles.items():
        overlaps = [[] for _ in scores]
        for word in words:
            if word in lookup:
                index, score = lookup[word]
                overlaps[index].append(score)
        totals = [round(fsum(values), 12) for values in overlaps]
        if any(overlaps):
            winner = max(range(len(scores)), key=lambda i: totals[i])
            assigned[words] = winner
            counts[winner] += count
        else:
            assigned[words] = None
    return assigned, counts


def _merge(graph, communities, profiles):
    while len(communities) > params.PERSONA_RANGE[1]:
        scores = [_centrality(graph.subgraph(c)) for c in communities]
        _, counts = _assign_profiles(profiles, scores)
        smallest = min(range(len(communities)), key=lambda i: (counts[i], i))
        owners = {word: i for i, community in enumerate(communities) for word in community}
        weights = Counter()
        for word in sorted(communities[smallest]):
            for neighbor, attributes in graph[word].items():
                target = owners[neighbor]
                if target != smallest:
                    weights[target] += attributes['weight']
        candidates = [i for i in range(len(communities)) if i != smallest]
        if weights:
            target = max(candidates, key=lambda i: (weights[i], -i))
        else:
            target = max(candidates, key=lambda i: (counts[i], -i))
        communities[target].update(communities[smallest])
        del communities[smallest]
        communities = _ordered(communities)
    return communities


def _network_view(graph, ranked):
    nodes = sorted((dict(id=word, persona=i, score=score)
                    for i, values in enumerate(ranked) for word, score in values),
                   key=lambda node: (-node['score'], node['id']))[:params.NETWORK_SHOW]
    shown = {node['id'] for node in nodes}
    edges = [dict(source=a, target=b, weight=data['weight'])
             for a, b, data in sorted(graph.edges(data=True)) if a in shown and b in shown]
    return dict(nodes=nodes, edges=edges)


def personas(cluster_ids: list[str], nouns: dict, bk: str) -> PersonaResult:
    """Partition one cluster; missing noun entries behave as empty documents.

    Vocabulary/edge frequencies count document presence, never repetitions.
    All ranking ties use lexical noun order or the lowest Persona index.
    Empty/edgeless input produces one Persona with 'few_communities'.

    quality.resample_ari's adapter is recluster(indices, rng): map indices to
    cluster_ids, call personas(sampled_ids, nouns, bk), then return
    [result.assign[d] for d in sampled_ids]. Louvain always uses params.SEED;
    the supplied rng controls quality's sampling, not Persona partitioning.
    """
    ids = sorted(set(cluster_ids))
    frequencies = Counter()
    for doc_id in ids:
        frequencies.update(word for word in set(nouns.get(doc_id, ())) if word and word != bk)
    vocabulary = set(sorted(frequencies, key=lambda w: (-frequencies[w], w))[:params.L2_VOCAB])
    # Repeated noun profiles are common; aggregate them before pair counting
    # and document scoring, keeping the expensive graph work vocabulary-bound.
    profiles = Counter(tuple(sorted(vocabulary.intersection(nouns.get(d, ())))) for d in ids)
    pairs = Counter()
    for words, count in profiles.items():
        for pair in combinations(words, 2):
            pairs[pair] += count
    graph = nx.Graph()
    graph.add_nodes_from(sorted(vocabulary))
    graph.add_weighted_edges_from((a, b, count) for (a, b), count in sorted(pairs.items())
                                 if count >= len(ids) * params.L2_EDGE_MIN_DOC_RATIO)
    if not graph.number_of_edges():
        communities = [set(graph)]
    else:
        for resolution in params.L2_RESOLUTIONS:
            communities = _ordered(nx.community.louvain_communities(
                graph, weight='weight', resolution=resolution, seed=params.SEED))
            if len(communities) >= params.PERSONA_RANGE[0]:
                break
        communities = _merge(graph, communities, profiles)
    scores = [_centrality(graph.subgraph(c)) for c in communities]
    assigned, counts = _assign_profiles(profiles, scores)
    largest = max(range(len(communities)), key=lambda i: (counts[i], -i))
    assign, reasons = {}, {}
    fallback = 0
    for doc_id in ids:
        words = tuple(sorted(vocabulary.intersection(nouns.get(doc_id, ()))))
        winner = assigned[words]
        is_fallback = winner is None
        assign[doc_id] = largest if is_fallback else winner
        reasons[doc_id] = 'fallback' if is_fallback else 'centrality'
        fallback += is_fallback
    ranked = [sorted(values.items(), key=lambda item: (-item[1], item[0])) for values in scores]
    return PersonaResult(
        assign=assign, communities=[sorted(c) for c in communities],
        centrality=[values[:params.CENTRALITY_TOP] for values in ranked],
        network=_network_view(graph, ranked),
        flags=['few_communities'] if len(communities) < params.PERSONA_RANGE[0] else [],
        fallback_ratio=fallback / len(ids) if ids else 0., assignment_reasons=reasons)
