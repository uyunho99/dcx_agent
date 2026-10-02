# Task T4 report

- status: complete
- executor: codex
- scope: DCX 2.0 stage 6 bundle 1, L2 Persona (1.0 Actor)

## Files

- `backend/app/segment/l2.py` — noun-network construction, Louvain partitioning, granularity enforcement, eigenvector scoring, document assignment and view projection.
- `backend/tests/segment/test_l2.py` — 17 offline test cases.
- `.superpowers/sdd/03-plan/task-T4-report.md` — this report.

No other files changed; no git add/commit, network access, subagents or reviewers.

## RED

Wrote the tests before creating the implementation. Ran:

```text
backend/.venv/bin/python -m pytest backend/tests/segment/test_l2.py -q
```

Result: exit 2, collection failure because `app.segment.l2` did not exist.
The first implementation run had 14 passing cases and two test-fixture
assumptions to correct: a subsequent legal merge could reunite the groups
used to test the first merge, and resolution escalation can split a two-node
graph. Added a stronger second merge neighbor and made the tiny-input flag
assertion conditional on the actual community count. Added an analytical star
graph check for centrality values and weighted assignment.

## GREEN and refactor

Implemented using the committed params unchanged:
`L2_VOCAB=300`, `L2_EDGE_MIN_DOC_RATIO=0.005`,
`L2_RESOLUTIONS=(1.0,1.2,1.5,2.0)`, `PERSONA_RANGE=(2,3)`,
`CENTRALITY_TOP=16`, `NETWORK_SHOW=60`, `SEED=42`.

The focused suite passed, then `_network_view` was extracted to separate
display truncation from assignment. Final focused rerun:

```text
backend/.venv/bin/python -m pytest backend/tests/segment/test_l2.py -q
17 passed, 1 warning in 3.09s
```

Coverage includes all five synthetic clusters (expected 2/3 Personas and
accuracy >= 0.9), merge by summed edge weights, disconnected merge into the
largest document community, resolution escalation and early stopping,
fallback reasons/ratio, product exclusion, document-presence edge weights,
inclusive .005 edge threshold, vocabulary cap, weighted eigenvector scores,
assignment using all nouns rather than only the displayed 16, the 60-node
view with valid edge endpoints, empty/missing/tiny inputs, reordered-input
determinism and the real quality ARI adapter.

## Full suite

Executed exactly once after refactoring:

```text
backend/.venv/bin/python -m pytest backend/tests -q
1590 passed, 2 deselected, 2 warnings in 150.91s (0:02:30)
```

Warnings came from the existing Pydantic class-based settings configuration
and joblib physical-core detection. Tests enforce offline socket access.

## Exact callable shape for quality's ARI resampler

The public API remains:

```python
personas(cluster_ids: list[str], nouns: dict, bk: str) -> PersonaResult
```

`quality.resample_ari` requires `recluster(indices, rng) -> labels`, with labels
in sampled-index order. For one L1 cluster, use the following adapter; `vectors`
must have rows in exactly `cluster_ids` order:

```python
from app.segment.l2 import personas
from app.segment.quality import resample_ari

baseline = personas(cluster_ids, nouns, bk)
labels = [baseline.assign[doc_id] for doc_id in cluster_ids]

def recluster(indices, rng):
    sampled_ids = [cluster_ids[int(i)] for i in indices]
    result = personas(sampled_ids, nouns, bk)
    return [result.assign[doc_id] for doc_id in sampled_ids]

ari = resample_ari(vectors, labels, level='L2', recluster=recluster)
```

The adapter accepts `rng` for the callback contract. Quality uses it for
resampling; Louvain always receives `seed=params.SEED`. No global random state
is changed. The adapter is exercised through the real resampler in the tests.

## Self-review

- `communities` and `centrality` are lists indexed by zero-based Persona index;
  communities contain sorted complete vocabularies. The stable lexical order
  supplies tie breaks and local indices. Centrality lists contain up to 16
  `(word, score)` pairs, without inventing padding for smaller communities.
- `network` is a cluster-level view. Nodes are `{id, persona, score}`; edges
  are `{source, target, weight}`. The display cap never truncates the assignment
  vocabulary or centrality calculation.
- `assignment_reasons[doc_id]` records `centrality` or `fallback`. Fallbacks
  are assigned after scoring all overlapping documents, so input order cannot
  influence which Persona is largest. The denominator is unique input docs;
  empty input returns ratio 0 and one empty Persona with `few_communities`.
- Community size means currently assigned non-fallback document count. Counts
  are recomputed after each merge; ties use stable lexical community order.
- Co-occurrence weights count each unordered noun pair once per document.
  Only requested cluster documents affect vocabulary/frequencies. Identical
  noun profiles are aggregated to avoid repeating pair and score calculations.
- Calls `networkx.community.louvain_communities` and
  `networkx.eigenvector_centrality_numpy` with explicit edge weights. Isolated
  vocabulary nodes are retained, and an edgeless graph bypasses Louvain and
  returns one Persona with `few_communities`.
- Installed NetworkX 3.7 rejects disconnected eigenvector input. Merged islands
  therefore use eigenvector centrality per connected component, each normalized
  to max 1. Singleton/pair components use the equal analytical value 1, avoiding
  ARPACK's small-matrix limitation. Scores are rounded to 12 decimals before
  ranking/assignment to remove numerical tie noise. Repeated and reordered
  input tests pass with identical full results.
- File-scope check showed only the two owned implementation/test files before
  writing this report. No committed interfaces or background files were edited.

## Concerns

- Design section 3.3 mentions stopwords but the brief, params and input contract
  supply no stopword list. This implementation excludes exact product name `bk`
  and empty tokens; it does not invent a language-specific stopword dictionary.
- Component-wise normalization for disconnected merged communities is an
  explicit convention, since a unique whole-graph eigenvector does not exist
  in general and NetworkX rejects such input.
- Real 310k–1m-document throughput was not benchmarked in T4. Graph vocabulary
  is bounded at 300 and repeated noun profiles are aggregated; highly varied,
  long noun sets still require pair enumeration per unique profile.

## Fix round 1

Implemented both Important review findings and the controller ruling. This
supersedes the original self-review's isolated-node retention and independent
component-max normalization conventions.

- Remove zero-degree nodes after edge thresholding and before Louvain; rebuild
  the scoring vocabulary/profiles so isolated-only documents take the unscored
  fallback path and isolated nouns cannot appear in communities or network views.
- Normalize each Persona's main-component hub to 1.0. Component weight is the
  sum of retained co-occurrence edge weights; other component maxima are scaled
  by their weight divided by the largest component weight. Singleton components
  score zero; pairs receive the relative-weight scale, not an automatic 1.0.
  Zero-score overlap does not count as a scored document assignment.
- Drop communities with no assigned non-fallback documents before testing the
  Persona range at each resolution and before/after merges. Ignore neighbors
  belonging to dropped communities when choosing merge targets. If one supported
  community remains, retain resolution retries and the `few_communities` flag.
- Preserve `personas(cluster_ids, nouns, bk) -> PersonaResult`; no stopword list,
  parameter changes, dependency changes, git add/commit, or subagents.

### Regression coverage and TDD

Added five regression cases before editing the implementation:

- `test_rare_isolated_nouns_do_not_displace_hub`: two clean eight-noun groups
  with strengthened hubs plus 60 documents carrying distinct rare nouns; the hub
  stays at 1.0, rare nouns are absent from top-16/communities/network, and all 60
  rare-only documents are fallbacks with the correct ratio.
- `test_rare_isolated_nouns_do_not_create_junk_persona`: the same reproduction
  returns exactly two distinct, document-supported Personas.
- `test_merged_components_scale_by_relative_edge_weight`: analytical weighted
  star plus disconnected pair and singleton; hub 1.0, leaves 0.5, pair 0.05,
  singleton 0.0.
- `test_zero_document_communities_dropped_before_persona_range` (two and four
  candidate communities): tied overlaps leave one supported Persona; all
  resolutions are tried, unsupported communities are dropped before range/merge
  decisions, and `few_communities` is emitted without introducing fallbacks.

RED command (before implementation changes):

```text
backend/.venv/bin/python -m pytest backend/tests/segment/test_l2.py backend/tests/segment/test_pipeline.py -q
5 failed, 30 passed, 2 warnings in 25.69s
```

All five new cases failed as intended: rare nouns entered the hub ranking,
three Personas appeared instead of two, the small pair scored 1.0 instead of
0.05, and both unsupported-community cases stopped at the first resolution.

GREEN command:

```text
backend/.venv/bin/python -m pytest backend/tests/segment/test_l2.py backend/tests/segment/test_pipeline.py -q
35 passed, 2 warnings in 27.93s
```

Full suite, executed once after the fix:

```text
backend/.venv/bin/python -m pytest backend/tests -q
1618 passed, 2 deselected, 2 warnings in 186.42s (0:03:06)
```

Warnings remain the existing Pydantic class-based settings deprecation and
joblib physical-core detection warning. No new concerns identified. Changes
are limited to `backend/app/segment/l2.py`, `backend/tests/segment/test_l2.py`,
and this appended report section.
