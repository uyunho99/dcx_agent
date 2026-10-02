# T10 report — stage 7 assembly, metrics, package and report

## Scope and status

Implemented job A and T10 in the assigned worktree. No frontend files were edited by this task; no staging, commits, or subagents were used. Existing concurrent changes were left untouched.

Files added:
- `backend/tests/evidence/__init__.py`
- `backend/app/evidence/assemble.py`
- `backend/tests/evidence/test_assemble.py`

## Job A — collection repair

Added the package marker following the existing `tests/segment` convention. Before adding T10 tests:
- `backend/.venv/bin/python -m pytest backend/tests/evidence -q`: **154 passed, 2 warnings**.
- `backend/.venv/bin/python -m pytest backend/tests -q --co`: **1869/1871 tests collected (2 deselected)**, exit 0; no import-file-mismatch.

## T10 implementation

- Counter evidence: relevant Counter-hit candidates, inclusive `polarity <= Context mean - 0.3`, descending relevance with document-ID tie breaking, maximum five. The Context mean uses available polarities of relevant tagged assigned documents.
- Rare evidence: relevant edge candidates with pain point or unmet need, ranked by the shared quality formula, maximum five regardless of main selection.
- Undifferentiated candidates: inspect the entire rare pool, require three mutually similar documents at cosine >= 0.8 (a connected chain does not qualify), ignore absent/zero/nonfinite vectors. Preserve three IDs in evidence Context `counts.undifferentiated` and report `escalation_candidates`. A small transaction helper appends `undifferentiated_candidate` to segment Context `flags_json` without replacing other flags or changing SegmentStore public behavior.
- Desire support: consume ranked persona-query all-tab results persisted as `persona_support(kind='desire')`, retain Known matches, exclude irrelevant/untagged rows, take five distinct documents.
- Artifacts: aggregate all tagged Persona documents, lowercase, remove whitespace, apply `filter_words(..., bk)` with normalized product name, count mentions and sort deterministically.
- Context metrics: sum assigned theta / Persona document count, session min-max; mean stored KNU sentiment mapped to 0..1 then session min-max; ODI `I + max(I-S, 0)`; document count and distinct nonempty document-author hashes. No comment authors. Pagination covers all documents. Unavailable observations remain null; constant observed ranges map to zero.
- Persona metrics: document-count-weighted Context metrics; document counts and distinct authors across the Persona. Provisional markers retained. Persona quality does not inherit unrelated Cluster quality; available L2 stability comes from stage-six reporting, unavailable values remain null.
- Package: read explicit version-local session/SegmentStore/EvidenceStore snapshot plus preparation documents/vectors and tag cache; reproject current Known IDs from pair cache; locate quotes against prepared originals; merge support tab membership and novelty; use confirmed names/actions and dims-first situations. Validate with `EvidencePackage` and atomically write `evidence/package.json`.
- Report: write `evidence/stage_7.json` with per-Context coverage /6, coverage supplements, band exposure ratios, novelty distribution, escalation IDs, relevant-false/reason distribution, query failures, per-tab counts, Known distribution, expansions, rare fallback, DPP fill, untagged, lazy dims, LLM calls, cache hits and parameter values. Explicit field whitelist excludes A–C agreement.
- Assembly performs no LLM, embedding, or search calls.

## Worker handoff / conventions

The T11 worker owns run locking, version writability, search/tag/select orchestration and completion. Before `assemble(sid, version)`, persist ranked persona-query all-tab rows in `persona_support` and runtime counters in `contexts.counts`: `coverage_supplements`, `query_gen_fail`, `new_expansions`, `rare_fallback`, `dpp_fill`, `lazy_dims`, `llm_calls`, `cache_hits` (scalar counts). Assembly sums these counters and derives observable distributions from persisted rows. Cache hits represent worker tagging activity, not assembly's read of the cache.

Report exposure and Known distributions count selected row appearances across tabs; tagging rejection/untagged totals count distinct attempted documents. All tab counts include explicit zeros. These conventions are documented in the module and tested. Package and report are each atomically replaced; orchestration remains responsible for serializing assembly with other writers.

## Verification

TDD RED: new test module failed collection because `app.evidence.assemble` did not exist (1 error, expected). Implementation then reached 8 passed / 1 failed, exposing tuple/list serialization inequality; normalized recorded params to JSON-native values. Initial GREEN: **9 passed**. Additional pagination and real synthetic stage-six integration checks: **11 passed, 2 warnings**. Tests cover exact thresholds, non-clique rejection, flag idempotence, Known retention/deletion, artifacts, metric formulas/missing values, persisted package validation, report fields and repeat assembly.

`git diff --check` passed.

Full backend suite, run exactly once after implementation:

`backend/.venv/bin/python -m pytest backend/tests -q`

**1880 passed, 2 deselected, 2 warnings in 305.43s (0:05:05)**, exit 0.

Warnings are the existing Pydantic class-based-config deprecation and joblib physical-core detection fallback. No test failures or collection errors remain. No blocking concerns; T11 must honor the worker handoff conventions above.
