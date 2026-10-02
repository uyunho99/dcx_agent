# T12 — Stage 7 FastAPI router

Status: PASS — implementation and required validation complete.

## Changes

- Added `backend/app/routers/evidence.py` and registered it in `backend/app/main.py`.
- Implemented all seven endpoint contracts with optional version selection, shared StoreError/validation mapping, writable-version guards, and worker launch through `runner`.
- Run rejects unfinished, unconfirmed, empty, or stale stage-six results with HTTP 409 `segment_required` and the exact required Korean copy. Active evidence work returns `running`; other active version-local work returns `locked`.
- Status reads one EvidenceStore snapshot, returns frontend-compatible Context rows and numeric counts, detects changed Known IDs, and includes stage-seven report and worker interruption reason.
- Context reads use detached snapshot rows, support both tabs, and reject pending/unavailable results. Persona reads expose desire support and artifacts; package reads require completed evidence.
- Refresh and skip delegate to the committed pipeline generation-checked mutations. Refresh makes zero LLM calls; skip returns the full frontend status shape. Stale screen actions return HTTP 409 `stale_run`, including after stage-six invalidation.
- Kept view serialization and read-only document/cache loading in shared router helpers. Read endpoints do not run assembly, embedding, or LLM tasks.

## Contract decisions

- The brief's Known Insight shorthand says `from: 'rag'`, `docId`; the existing frontend actually posts `{type: 'doc', doc_id}`. Kept that existing endpoint and payload unchanged; its server assigns origin `rag` (wire field `from`). The integration test checks this behavior.
- The committed pipeline refresh response can contain a null quote, while `EvidenceItemView.quote` is non-nullable. The router returns `{text: '', start: null, end: null, verified: false}` for missing quotes, and strips the internal query owner field. No frontend edits were needed.
- Read-only write errors retain the existing shared `conflict` kind, consistent with the segment/session API.

## TDD and validation

- Wrote `backend/tests/evidence/test_api.py` before implementation; first run: **15 failed**, all due to missing HTTP routes (404).
- Implemented the router: **15 passed**.
- Added boundary coverage; observed **1 failed, 21 passed** when stale stage-six state reached worker launch. Added the router prerequisite check: **22 passed**.
- Coverage includes all routes, exact prerequisite copy, pending Context states, invalid/missing IDs and bodies, worker locks, read-only historical reads and rejected writes, stale UI actions, skip completion, Known add/refresh membership and zero LLM calls, quote-less items, version isolation, worker reasons, subset/fresh forwarding, and reset interleaving during snapshot reads.
- `npm --prefix frontend test` (run once): **56 test files passed; 522 tests passed**.
- `backend/.venv/bin/python -m pytest backend/tests -q` (run once): **1,944 passed, 2 deselected, 2 warnings in 309.45s**. Warnings: existing class-based Pydantic settings config deprecation and joblib physical-core detection fallback.
- `git diff --check`: passed.

## Concerns

- No blocking contract concerns identified. Known payload and quote differences are handled above.
- Read routes load requested original texts and cached tags but scan segment document metadata/prepared JSONL files; large-session HTTP performance was not benchmarked in this API task.
- No frontend files or existing pipeline/store files changed. No git add or commit performed.
