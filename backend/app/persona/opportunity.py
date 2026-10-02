"""Context opportunity coordinates and rendering metadata (D-225, D-307).

Means weight every Context equally. Cluster shapes follow first appearance in
the package; Persona tones cycle within each cluster, also in package order.
Selection blue is a UI state, so it is never persisted here.
"""
from typing import Literal

from app.persona.package import Package
from app.persona.params import S_LINE, STAR_MIN, STAR_NOVELTY

SHAPES = ('circle', 'square', 'triangle', 'diamond', 'pentagon')
TONES = ('--ink-strong', '--ink', '--line-strong')


def _mean(values: list[float], *, empty: float) -> float:
    return sum(values) / len(values) if values else empty


def baselines(points: list[tuple[float, float]]) -> dict:
    """Use neutral midpoint diagonals when there are no Contexts to average."""
    i_mean = _mean([i for i, _ in points], empty=.5)
    s_mean = _mean([s for _, s in points], empty=.5)
    return {'s_line': S_LINE, 'diag1': ((0, s_mean), (1, 1)),
            'diag2': ((i_mean, 0), (1, 1))}


def zone(i: float, s: float, base: dict) -> Literal['A', 'B', 'C', 'D', 'E', 'F']:
    """Assign equality to the upper side of every line, without an epsilon band.

    With I_mean=1, diagonal 2 is vertical at the right edge: no normalized
    point is below it. At the shared (1, 1) endpoint, diagonal 1 takes priority.
    """
    s_mean = base['diag1'][0][1]
    i_mean = base['diag2'][0][0]
    if s >= s_mean + (1 - s_mean) * i:
        return 'A' if s >= base['s_line'] else 'D'
    if i_mean < 1 and s < (i - i_mean) / (1 - i_mean):
        return 'C' if s >= base['s_line'] else 'F'
    return 'B' if s >= base['s_line'] else 'E'


def star(context: dict, odi_mean: float) -> bool:
    """Count qualifying entries in Context evidence, per the package contract."""
    return (sum(e['novelty'] in STAR_NOVELTY for e in context['evidence']) >= STAR_MIN
            and context['metrics']['odi'] >= odi_mean)


def build_map(package: Package) -> dict:
    """Return JSON-ready points, baselines and a Cluster → Persona legend.

    ``counter`` records the semantic flag; ``hollow`` is its rendering cue.
    ``cluster_label`` is the extra on-point label required for cluster six on.
    Coincident points remain separate, retaining their original Context IDs.
    """
    contexts = [c for block in package.personas for c in block.context_evidence]
    base = baselines([(c.metrics.importance, c.metrics.satisfaction) for c in contexts])
    odi_mean = _mean([c.metrics.odi for c in contexts], empty=0)
    clusters = {}
    points = []
    for block in package.personas:
        persona = block.persona_evidence
        cid = persona.cluster_id
        if cid not in clusters:
            index = len(clusters)
            clusters[cid] = {
                'cluster_id': cid,
                'shape': SHAPES[index] if index < len(SHAPES) else SHAPES[0],
                'cluster_label': cid if index >= len(SHAPES) else None,
                'personas': [],
            }
        cluster = clusters[cid]
        tone = TONES[len(cluster['personas']) % len(TONES)]
        cluster['personas'].append({'persona_id': persona.persona_id,
                                    'persona_name': persona.persona_name, 'tone': tone})
        for context in block.context_evidence:
            metrics = context.metrics
            counter = 'counter_context' in context.flags
            points.append({
                'context_id': context.context_id, 'persona_id': persona.persona_id,
                'cluster_id': cid, 'i': metrics.importance, 's': metrics.satisfaction,
                'odi': metrics.odi, 'zone': zone(metrics.importance, metrics.satisfaction, base),
                'star': star(context.model_dump(), odi_mean), 'counter': counter,
                'hollow': counter, 'shape': cluster['shape'], 'tone': tone,
                'cluster_label': cluster['cluster_label'],
            })
    return {'points': points, 'base': base, 'legend': list(clusters.values())}
