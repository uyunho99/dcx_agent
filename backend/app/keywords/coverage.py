"""Pure coverage metrics; no settings, network, or keyword mutations.

A human query matches an LLM keyword if norm_key(llm) is a substring of
norm_key(query) or vice versa. Empty normalized strings never match.
Deciles partition descending volume ranks into ten contiguous buckets;
remainder queries go to the first buckets. Axis distributions count items,
not search volume. Unknown counts do not qualify as LLM-only.
"""

from collections import Counter
from dataclasses import dataclass
from math import isfinite, log2, sqrt

from app.keywords.models import Keyword
from app.keywords.normalize import norm_key


@dataclass
class CoverageReport:
    m1: float | None
    m2: list[float | None]
    m6: float | None
    m7: float
    missing_top: list[tuple[str, int]]
    llm_only_ids: list[str]


def js_distance(p: dict, q: dict) -> float:
    """Base-2 Jensen–Shannon distance (square root of divergence).

    Inputs may be unnormalized nonnegative weights with positive totals.
    Empty/zero distributions are undefined and raise ValueError.
    """
    if any(not isfinite(v) or v < 0 for dist in (p, q) for v in dist.values()):
        raise ValueError('Distribution weights must be finite and nonnegative')
    pt, qt = sum(p.values()), sum(q.values())
    if pt <= 0 or qt <= 0:
        raise ValueError('Distributions must have positive totals')
    divergence = 0.0
    for key in p.keys() | q.keys():
        a, b = p.get(key, 0) / pt, q.get(key, 0) / qt
        midpoint = (a + b) / 2
        if a:
            divergence += a * log2(a / midpoint) / 2
        if b:
            divergence += b * log2(b / midpoint) / 2
    return sqrt(min(1.0, max(0.0, divergence)))


def _matches(a: str, b: str) -> bool:
    return bool(a and b) and (a in b or b in a)


def _weighted(rows: list[tuple[str, int, bool]]) -> float | None:
    total = sum(count for _, count, _ in rows)
    return sum(count for _, count, matched in rows if matched) / total if total else None


def compute(human: list[tuple[str, int]], llm: list[Keyword],
            human_axes: dict[str, str] | None = None) -> CoverageReport:
    """Compute metrics; absent human data yields None for m1/m2/m6.

    m7 uses the design's fixed <10 cutoff. With no human rows it uses
    available keyword volumes alone. Incomplete axis labels yield m6=None.
    The returned IDs let callers attach llm_only badges without side effects.
    """
    human_keys = [norm_key(query) for query, _ in human]
    llm_keys = [norm_key(kw.kw) for kw in llm]
    rows = sorted([(query, count, any(_matches(key, other) for other in llm_keys))
                   for (query, count), key in zip(human, human_keys)],
                  key=lambda row: row[1], reverse=True)
    size, remainder = divmod(len(rows), 10)
    deciles = []
    start = 0
    for index in range(10):
        end = start + size + (index < remainder)
        deciles.append(_weighted(rows[start:end]))
        start = end
    only_ids = []
    for kw, key in zip(llm, llm_keys):
        monthly = (kw.volume or {}).get('monthly')
        if monthly is not None and monthly < 10 and not any(
            _matches(key, other) for other in human_keys
        ):
            only_ids.append(kw.id)
    axis_distance = None
    axes = {'physical', 'psychological', 'behavioral'}
    if human and llm and human_axes is not None and all(human_axes.get(query) in axes for query, _ in human):
        axis_distance = js_distance(Counter(human_axes[query] for query, _ in human),
                                    Counter(kw.axis for kw in llm))
    return CoverageReport(
        m1=_weighted(rows), m2=deciles, m6=axis_distance,
        m7=len(only_ids) / len(llm) if llm else 0.0,
        missing_top=[(query, count) for query, count, matched in rows if not matched][:20],
        llm_only_ids=only_ids,
    )
