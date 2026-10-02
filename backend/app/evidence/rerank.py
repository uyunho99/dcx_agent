"""Pure quality, diversity and coverage selection for stage-seven evidence."""
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from app.evidence.params import (
    COVERAGE_EXTRA, COVERAGE_MIN, DPP_SIGMA, DUP_COSINE, RARE_MIN, SELECT_N,
    TAG_PROB_ON, W_RARITY,
)
from app.label.rule import SEM


@dataclass
class Selection:
    rows: list[dict]
    coverage: int
    missing_dims: list[str]
    rare_fallback: int
    coverage_supplements: int = 0
    dpp_fill: int = 0


def quality(relevance: float, combo_rarity: float | None, w_r=W_RARITY) -> float:
    """Known-Insight matches do not affect quality."""
    return float(relevance * (1 + w_r * (combo_rarity or 0.)))


def dpp_greedy(quality: np.ndarray, vectors: np.ndarray, k: int,
               sigma=DPP_SIGMA) -> list[int]:
    """Chen et al. (2018) incremental Cholesky greedy selection, O(n²d + nk²).

    Return up to k indices, breaking ties by input order. Stop when no positive
    conditional determinant remains (including duplicate/rank exhaustion).
    The specified squared-cosine-distance kernel is used without PSD repair;
    it need not be PSD for arbitrary inputs. Nonpositive pivots are ineligible.
    """
    q = np.asarray(quality, dtype=np.float64)
    v = np.asarray(vectors, dtype=np.float64)
    if q.ndim != 1 or v.ndim != 2 or len(q) != len(v):
        raise ValueError('quality and vectors must have matching rows')
    if not np.isfinite(sigma) or sigma <= 0:
        raise ValueError('sigma must be positive and finite')
    if not np.all(np.isfinite(q)) or not np.all(np.isfinite(v)):
        raise ValueError('quality and vectors must be finite')
    if k <= 0 or len(q) == 0:
        return []
    norms = np.linalg.norm(v, axis=1)
    if np.any(norms == 0):
        raise ValueError('vectors must have nonzero norms')
    unit = v / norms[:, None]
    cosine = np.clip(unit @ unit.T, -1., 1.)
    similarity = np.exp(-np.square(1. - cosine) / sigma ** 2)
    kernel = q[:, None] * similarity * q[None, :]
    remaining = np.diag(kernel).copy()
    coefficients = np.zeros((min(k, len(q)), len(q)))
    tolerance = np.finfo(np.float64).eps * len(q) * remaining.max()
    selected = []
    for step in range(min(k, len(q))):
        index = int(np.argmax(remaining))
        if remaining[index] <= tolerance:
            break
        selected.append(index)
        update = (kernel[index] - coefficients[:step, index] @ coefficients[:step])
        update /= np.sqrt(remaining[index])
        coefficients[step] = update
        remaining -= update ** 2
        remaining[selected] = -np.inf
    return selected


def _covered(doc_ids: list[str], tag_probs: dict[str, dict | None]) -> set[str]:
    return {dim for doc_id in doc_ids for dim in SEM
            if (tag_probs.get(doc_id) or {}).get(dim, 0.) >= TAG_PROB_ON}


def coverage(doc_ids: list[str], tag_probs: dict[str, dict | None]) -> int:
    """Count the union of the six lowercase stage-four/five semantic tags."""
    return len(_covered(doc_ids, tag_probs))


def _rare_swaps(selected: list[dict], candidates: list[dict]) -> tuple[list[dict], int]:
    selected = list(selected)
    needed = max(0, RARE_MIN - sum(row['rare'] for row in selected))
    if not needed:
        return selected, 0
    selected_ids = {row['doc_id'] for row in selected}
    remaining_rare = sorted(
        (row for row in candidates if row['rare'] and row['doc_id'] not in selected_ids),
        key=lambda row: (-row['quality'], row['doc_id']),
    )
    fallbacks = 0
    for rare in remaining_rare[:needed]:
        nonrare = [i for i, row in enumerate(selected) if not row['rare']]
        if not nonrare:
            break
        worst = min(nonrare, key=lambda i: (selected[i]['quality'], selected[i]['doc_id']))
        selected[worst] = rare
        fallbacks += 1
    return selected, fallbacks


def select(candidates: list[dict], tags: dict, vectors: dict, docs: dict, *,
           k=SELECT_N,
           supplement: Callable[[list[str], int], list[dict]] | None = None) -> Selection:
    """Select relevant, successfully tagged candidates without mutating inputs.

    ``supplement(missing_dims, 15)`` is called at most once, before rare swaps.
    It returns additional candidate rows; tags/vectors/docs must cover those IDs
    when it returns. Dimensions are lowercase export keys (capitalize to look
    up the corresponding query dimension). No search or other I/O lives here.
    Candidate combo_rarity overrides docs[doc_id].combo_rarity when supplied;
    band comes from the candidate, relevant/pain_point/unmet_need from tags,
    and coverage comes exclusively from docs[doc_id].tagProbs.
    Short DPP selections are filled in descending quality order, requiring
    cosine < DUP_COSINE against every selected row, before coverage and rare
    fallback handling. dpp_fill counts fills in the final selection pass.
    Rows retain DPP then fill order, with swaps occupying the removed row's rank.
    """
    rows_by_id = {}

    def add(rows):
        for candidate in rows:
            doc_id = candidate['doc_id']
            tag = tags.get(doc_id) or {}
            if doc_id in rows_by_id or not tag.get('relevant'):
                continue
            rarity = candidate.get('combo_rarity', docs[doc_id].get('combo_rarity'))
            rows_by_id[doc_id] = dict(
                doc_id=doc_id, quality=quality(candidate['relevance'], rarity),
                rare=bool(candidate.get('band') == 'edge'
                          and (tag.get('pain_point') or tag.get('unmet_need'))),
            )

    def choose():
        rows = list(rows_by_id.values())
        if not rows or k <= 0:
            return [], 0
        matrix = np.array([vectors[r['doc_id']] for r in rows], dtype=np.float64)
        indices = dpp_greedy(np.array([r['quality'] for r in rows]),
                             matrix, k)
        fills = 0
        if len(indices) < min(k, len(rows)):
            unit = matrix / np.linalg.norm(matrix, axis=1)[:, None]
            remaining = sorted(
                set(range(len(rows))) - set(indices),
                key=lambda i: (-rows[i]['quality'], rows[i]['doc_id']),
            )
            for i in remaining:
                if len(indices) >= k:
                    break
                if np.all(unit[indices] @ unit[i] < DUP_COSINE):
                    indices.append(i)
                    fills += 1
        return [rows[i] for i in indices], fills

    def covered(rows):
        ids = [row['doc_id'] for row in rows]
        return _covered(ids, {i: docs[i].get('tagProbs') for i in ids})

    add(candidates)
    selected, fills = choose()
    dims = covered(selected)
    supplements = 0
    if k > 0 and len(dims) < COVERAGE_MIN and supplement is not None:
        add(supplement([dim for dim in SEM if dim not in dims], COVERAGE_EXTRA))
        supplements = 1
        selected, fills = choose()

    selected, fallbacks = _rare_swaps(selected, list(rows_by_id.values()))
    dims = covered(selected)
    return Selection(
        rows=[dict(row, rank=rank) for rank, row in enumerate(selected, 1)],
        coverage=len(dims), missing_dims=[dim for dim in SEM if dim not in dims],
        rare_fallback=fallbacks, coverage_supplements=supplements, dpp_fill=fills,
    )
