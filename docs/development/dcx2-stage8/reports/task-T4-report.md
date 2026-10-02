# T4 report — complete

Implemented only the four owned source/test files and this report. No staging or commits, no subagents, and no edits to T2/T3 files.

## Implementation

- `backend/app/persona/opportunity.py`: `baselines`, `zone`, `star`, `build_map` follow the brief and design section 5.5. Baselines and ODI mean use every Context with equal weight. Exact horizontal/diagonal boundaries belong to the upper zone (D-307); diagonal 1 wins at their shared endpoint. Vertical diagonal 2 at I_mean = 1 avoids division by zero.
- Shapes in package cluster order: `circle`, `square`, `triangle`, `diamond`, `pentagon`; sixth and later use `circle` plus `cluster_label`. Persona tones cycle per cluster through `--ink-strong`, `--ink`, `--line-strong`. Selection blue remains UI state.
- Each point contains the specified contract fields plus `hollow` (equal to `counter`) and `cluster_label` (null for the first five clusters). The legend is a list of `{cluster_id, shape, cluster_label, personas: [{persona_id, persona_name, tone}]}`. Coincident points retain distinct Context IDs.
- Stars count qualifying entries in Context `evidence`: novelty in `('high', 'very_high')`, count >= 2, and Context ODI >= the session Context mean, matching T1's fixture convention.
- `backend/app/persona/tree.py`: product root with Cluster → Persona → Context children. Nodes contain `{id, name, type, size, children}`. Persona and Context sizes use their own source `doc_count`; Cluster/product sizes sum Persona counts. Confirmed names and package ordering are preserved; Cluster IDs supply labels because the package contract lacks Cluster names.
- `params.py` was absent at initial inspection but arrived before implementation. Its exact `S_LINE`, `STAR_NOVELTY`, and `STAR_MIN` constants are imported; no local fallback was needed or written.
- Empty maps use neutral diagonal means of 0.5; empty trees have size 0. These deterministic empty-input defaults are implementation choices beyond the brief.

## TDD and verification

Command for all three runs:

```text
backend/.venv/bin/python -m pytest backend/tests/persona/test_opportunity.py backend/tests/persona/test_tree.py -q
```

1. RED: exit 2, two collection errors (`ModuleNotFoundError` for the unimplemented `opportunity` and `tree` modules).
2. GREEN: 33 passed, 1 warning in 2.30s.
3. Refactored repeated mean calculation into a private helper; final run: **33 passed, 1 warning in 2.38s**, exit 0.

Coverage includes six representative zones, exact horizontal and both diagonal boundaries, immediately-below-line values, degenerate diagonals, novelty/count/ODI star thresholds, fixture's two stars, six cluster shapes/labels, three cycling tones, nested legend, counter hollow flag, preserved overlapping points, JSON serialization, input immutability, tree hierarchy/grouping and source sizes, and empty inputs.

## Concerns

No blocking concerns. One existing `PydanticDeprecatedSince20` warning originates in `backend/app/config.py:12` (class-based Config); untouched. Downstream renderers should consume the documented legend, `cluster_label`, and `hollow` fields. Cluster/product tree counts are aggregate Persona counts, not document-ID deduplication; the package exposes counts rather than complete membership lists. Validation was limited to the requested T4 suite.
