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
from typing import Literal

from app.keywords.models import Keyword
from app.keywords.normalize import norm_key


@dataclass
class CoverageReport:
    m1: float | None
    m2: list[float | None] | None
    m6: float | None
    m7: float | None
    missing_top: list[tuple[str, int]]
    llm_only_ids: list[str]
    m2_bands: list[dict[str, str | float | None]] | None = None
    m7_reason: str | None = None


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


def _weighted(rows: list[tuple[str, int, bool]],
              weighting: Literal['volume', 'rank'] = 'volume') -> float | None:
    weights = [(1 / count if weighting == 'rank' else count, matched)
               for _, count, matched in rows]
    total = sum(weight for weight, _ in weights)
    return sum(weight for weight, matched in weights if matched) / total if total else None


def without_product_query(human: list[tuple[str, int]], bk: str) -> list[tuple[str, int]]:
    """Exclude the normalized product-only query from autocomplete coverage."""
    product_key = norm_key(bk)
    return [row for row in human if not product_key or norm_key(row[0]) != product_key]


def compute(human: list[tuple[str, int]], llm: list[Keyword],
            human_axes: dict[str, str] | None = None,
            weighting: Literal['volume', 'rank'] = 'volume', bk: str = '') -> CoverageReport:
    """Compute metrics; absent human data yields None for m1/m2/m6.

    m7 uses the design's fixed <10 cutoff. With no human rows it uses
    available keyword volumes alone; no known volumes yields m7=None.
    Incomplete axis labels yield m6=None.
    The returned IDs let callers attach llm_only badges without side effects.
    Rank mode expects ranks 1–10, uses reciprocal weights and three fixed
    bands, excludes product-only queries and also matches product-stripped queries,
    and leaves volume-dependent m7 and LLM-only badges unavailable.
    """
    rank_mode = weighting == 'rank'
    product_key = norm_key(bk) if rank_mode else ''
    if rank_mode:
        human = without_product_query(human, bk)
    human_keys = [norm_key(query) for query, _ in human]
    llm_keys = [norm_key(kw.kw) for kw in llm]
    def matched(key):
        remainder = norm_key(key.replace(product_key, '').strip()) if product_key and product_key in key else ''
        return any(_matches(key, other) or _matches(remainder, other) for other in llm_keys)

    rows = sorted([(query, count, matched(key))
                   for (query, count), key in zip(human, human_keys)],
                  key=lambda row: row[1], reverse=not rank_mode)
    bands = None
    deciles = None
    if rank_mode:
        bands = [
            {'label': f'{low}~{high}위',
             'value': _weighted([row for row in rows if low <= row[1] <= high], weighting)}
            for low, high in ((1, 3), (4, 6), (7, 10))
        ]
    else:
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
        if not rank_mode and monthly is not None and monthly < 10 and not any(
            _matches(key, other) for other in human_keys
        ):
            only_ids.append(kw.id)
    axis_distance = None
    axes = {'physical', 'psychological', 'behavioral'}
    if human and llm and human_axes is not None and all(human_axes.get(query) in axes for query, _ in human):
        axis_distance = js_distance(Counter(human_axes[query] for query, _ in human),
                                    Counter(kw.axis for kw in llm))
    return CoverageReport(
        m1=_weighted(rows, weighting), m2=deciles, m6=axis_distance,
        m7=len(only_ids) / len(llm) if not rank_mode and any(
            (kw.volume or {}).get('monthly') is not None for kw in llm
        ) else None,
        missing_top=[(query, count) for query, count, matched in rows if not matched][:20],
        llm_only_ids=only_ids,
        m2_bands=bands,
        m7_reason='no_volume' if rank_mode else None,
    )
