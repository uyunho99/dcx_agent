# Task T7 report

- status: complete
- executor: codex
- Scope: stage 6.5 Core context_dims extraction, normalization, pair frequencies, rarity, and Context summaries.

## Files

- `backend/app/segment/dims.py` — required Pydantic output schema; Core theta-ranked sampling; batched extraction through `registry.run_task`; one-to-one response-ID validation and retry; prompt-hashed, version-independent SQLite cache; phrase validation; deterministic greedy code normalization; sample pair counts; reusable `combo_rarity`; atomic SegmentStore updates; stage_6.dims diagnostics.
- `backend/app/segment/prompts/dims.v1.md` — Korean observed-only extraction instructions, required nullable keys, noun phrases at most 12 characters, no inference or LLM counting.
- `backend/tests/segment/test_dims.py` — 17 offline tests.
- `.superpowers/sdd/03-plan/task-T7-report.md` — this report.
- No shared fixtures were changed. `segment_synth.fake_dims_backend(...)` supplies batch-bound responses; the original `segment.dims.json` validates against the actual DimsOut model.

## RED

Command: `backend/.venv/bin/python -m pytest backend/tests/segment/test_dims.py -q`

Tests were written before implementation. Initial run failed collection because `app.segment.dims` did not exist (1 error). During implementation the test setup was corrected to use valid collection/prep references and a fake embedder. Initial GREEN: 14 passed.

Self-review added a failing assertion that overlength phrases must also be null inside the persistent cache, plus prompt-invalidation, reverse Act-mismatch, and two-pair lazy-rarity coverage. That run produced 1 failed, 16 passed; the failure demonstrated that the initial implementation cached an uncleaned phrase.

## GREEN and refactor

Final focused command: `backend/.venv/bin/python -m pytest backend/tests/segment/test_dims.py -q`

Result: **17 passed, 1 warning in 2.02s**. Phrase validation was factored into `_clean` and moved before cache insertion; a per-row diagnostic count preserves overlength counts on cache hits. Extraction, source streaming, code mapping, rarity, and summaries are separate helpers.

Coverage includes Core-versus-band selection, top-100 cap per Context, batches of 10, cross-version cache reuse without LLM calls, prompt hash invalidation, missing/duplicate/outside IDs with recovery and exhausted retry, null versus absent rows, required schema keys, phrase length boundaries, cosine grouping with non-unit vectors and below-threshold separation, representative frequency, both pair counts, rarity monotonicity and frozen lazy scale, unseen phrases, empty inputs, both Act mismatch directions, and persisted Context/code/combo/doc results.

## Full suite

Command (run once): `backend/.venv/bin/python -m pytest backend/tests -q`

Result: **1559 passed, 2 deselected, 2 warnings in 149.93s**. Exit code 0. No environment-only failures. Warnings: existing Pydantic class-based config deprecation and joblib physical-core discovery falling back to logical cores. Log: `/tmp/task-T7-full-suite.log`.

## Self-review

- Parameters use `params.DIMS_PER_CONTEXT`, `DIMS_BATCH`, `DIMS_PHRASE_MAX`, and `CODE_COS` without changing committed values.
- Cache identity is `llmcache/{sid}/{prepKey}/dims-{sha256(prompt bytes)}.sqlite`; no segment version is included. Rows contain cleaned dimensions, origin, configured model identity, and overlength diagnostics.
- Each malformed-ID response is rejected as a whole before any cache write. Retry once; exhausted batches are listed in `dims_failed` and excluded from observed-null statistics.
- Source shards and label export are streamed, retaining sampled documents only; no vector matrix or tokenizer work is performed.
- Greedy grouping processes phrases by descending frequency, then lexical tie-break, within each dimension. Representatives stay fixed. Failed/zero embeddings cannot merge unrelated phrases.
- Store writes replace only code/combo tables and update rarity and Context summary fields in one transaction, preserving names, flags, confirmations, and other layer data.
- `combo_rarity(dims_by_doc, codes, combos)` accepts raw phrase dictionaries and lists of persisted code/combo rows. It maps lazy phrases against the fixed representatives; unseen codes use frequency zero.
- `git diff --check` passed. Only authorized source/test files and this report were written. No git add/commit and no subagents were used.

## Concerns / integration conventions

No blocking concerns.

- Rarity uses `-log((count + 1) / N)` per pair. The `log(N)` term cancels under min-max normalization, so persisted pair counts suffice for lazy extraction. Bounds come from observed sample pairs, lazy values are clipped to [0,1], missing dimensions contribute zero, and zero-spread samples assign observed pairs 0 / unseen pairs 1. These degenerate-case conventions are documented and tested.
- Empty goal-or-constraint ratios use successful extractions as the denominator. Failed IDs, extracted counts, and sampled counts are separately exposed so failures are not mistaken for unobserved values.
- Per-Context ratios and mismatch counts are in the returned `contexts` mapping; the existing Context table receives `dominant_constraint` and dimension top-three `dims_summary`. The caller is responsible for saving the returned stage_6.dims payload.
- The registry has its own parse/schema retries; the additional retry here specifically enforces batch-ID integrity and retries unsuccessful task results. The cache records configured backend model/profile identity because LLMResult does not expose the resolved model.
