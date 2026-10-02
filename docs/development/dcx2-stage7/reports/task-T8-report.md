# T8 report — reranking and selection

Status: complete. No staging or commits. No subagents. Other workers' query/candidate files were not changed.

## Delivered

- `backend/app/evidence/rerank.py`: `quality`, Chen-style incremental Cholesky `dpp_greedy`, six-dimension `coverage`, `select`, and `Selection` result dataclass.
- `backend/tests/evidence/test_rerank.py`: 30 passing cases, including all required brief cases and numerical/input boundary checks.
- All tuning values imported from committed `params.py`: rarity weight 0.3, sigma 0.3, selection 10, coverage minimum 4, supplement 15, probability threshold 0.5, rare minimum 2. Known matches never affect quality.
- Export inspection: `model/export.py` preserves semantic dictionary keys in `tagProbs`; `segment/inputs.py` retains export fields. The canonical six lowercase names come from `app.label.rule.SEM`: sense, feel, think, act, relate, outcome. Anchor and situation are excluded. Null/missing tagProbs contributes zero dimensions.
- Relevant tagged candidates only; duplicate doc IDs merged once. Rare means edge band plus relevant plus pain_point or unmet_need. Swaps replace lowest-quality non-rare rows with highest-quality remaining rare rows until two are present or replacements run out. Each replacement increments `rare_fallback`. Final coverage is recomputed after swaps.

## Integration contract

`select(candidates, tags, vectors, docs, *, k=SELECT_N, supplement=None)` preserves the brief's positional interface and adds the requested injectable callback.

`supplement(missing_dims: list[str], count: int) -> list[dict]` receives lowercase semantic export keys and count 15. The caller maps these keys to query dimension names (for example, sense → Sense), performs retrieval/tagging outside this module, and ensures tags/vectors/docs contain metadata for the returned IDs by callback return. Alternatively, mappings can be prehydrated. Callback is optional, invoked at most once when initial coverage is below four and k is positive; its exceptions propagate. Selection reruns over the merged candidate pool even if coverage stays low. `coverage_supplements` records the invocation count.

Candidate rows provide doc_id, relevance, band, and optionally combo_rarity; otherwise combo_rarity is taken from docs and defaults to None. Tags provide relevant, pain_point, and unmet_need. Docs provide tagProbs; vectors are keyed by doc_id. Returned rows contain doc_id, quality, rank (one-based), rare. DPP order is retained; swaps occupy the removed row's rank. Result also contains coverage, missing_dims (lowercase, canonical order), rare_fallback, coverage_supplements. Inputs are not mutated by this module.

## TDD and verification

1. Wrote required test file before implementation.
2. RED: exact requested pytest command failed during collection with `ModuleNotFoundError: No module named 'app.evidence.rerank'` (exit 2).
3. GREEN: initial implementation passed 23 tests.
4. Added numerical and invalid-input checks: 30 passed.
5. Refactored rare fallback into a separate pure helper, including an early return when two rare rows are already selected. Re-ran the requested command:

   `backend/.venv/bin/python -m pytest backend/tests/evidence/test_rerank.py -q`

   **30 passed, 1 warning in 0.07s** (exit 0). Warning is the existing Pydantic class-based Config deprecation in `backend/app/config.py`.

The small-n test uses n=8, k=3 across five seeds and exhaustively evaluates every possible next candidate's log-determinant gain at each step, checking the full greedy order rather than asserting global combinatorial optimality. Additional checks cover scaled duplicate vectors, tiny quality scale, empty/zero budgets, exhausted pivots, short pools, default ten selections, null tags, one-shot/no-op supplementation, relevance filtering, two required swaps, final coverage after fallback, and input immutability.

## Concerns

- The exact required kernel `exp(-(1-cos)^2 / sigma^2)` is not guaranteed positive semidefinite for arbitrary vectors. The implementation preserves it verbatim, performs no spectral repair, and stops if no positive conditional determinant remains. Thus duplicates or nonpositive remaining pivots can produce fewer than min(k, n) rows. A regression test covers a non-PSD three-vector example. This is a mathematical limitation of the specified kernel, not a changed tuning value.
- Supplement hydration/query translation must be wired by the caller using the documented callback contract. No network or storage operations are introduced here.

## Fix round 1

- Implemented controller ruling D-257 in `select()`: after a short DPP result, scan remaining candidates in descending quality order (doc_id breaks ties), appending only candidates with cosine strictly below `params.DUP_COSINE` (0.95) against every currently selected document, including earlier fills. Stop at k or when eligible candidates are exhausted. The DPP kernel and pivot stopping rule are unchanged.
- Added `Selection.dpp_fill`, defaulting to zero. It records the number of slots filled in the final selection pass; a coverage supplement reruns selection and replaces the initial pass's count. Existing one-shot coverage supplementation and rare swaps remain after the fill, with final coverage recomputed as before.
- Added the three requested tests first: `test_dpp_short_fills_non_duplicates`, `test_dpp_short_no_fill_when_only_duplicates`, and `test_selection_reports_dpp_fill`. A deterministic fixture with three identical vectors plus nine distinct vectors exercises an actual nine-row DPP stop, then fills to ten while retaining only one identical vector. Five identical vectors yield one row and zero fills. Reporting also covers ordinary, empty, and zero-budget selections.
- RED: reranking suite produced **3 failed, 30 passed** before implementation (nine instead of ten selections; missing `dpp_fill` field). GREEN: **33 passed, 1 warning** after implementation.
- Final required verification: `backend/.venv/bin/python -m pytest backend/tests/evidence -q` — **113 passed, 2 warnings in 7.57s**. Warnings are the existing Pydantic Config deprecation and joblib physical-core detection fallback. `git diff --check` passed.
- Concerns: no new blockers. Fewer than k rows remain intentional when no nonduplicate fill candidates qualify. Rare swaps retain their existing behavior as required. No staging, commits, or subagents; the pre-existing decision-log change was left untouched.
