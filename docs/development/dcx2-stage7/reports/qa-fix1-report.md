# Stage 7 browser QA fix round 1

Implemented D-267 and D-268 on `feature/dcx2-stage7`.

## Changes

- Added optional `evidence.{queries,tag,novelty}.echo.json` markers and attachment-derived fake builders. Explicit responses, no-attachment example calls, and fixture directories without markers continue to use static JSON.
- Queries anchor every supplied Context ID, contain all eight dimensions, remove forbidden wording, and use first-person sentences.
- Tags return exactly the requested document IDs with verbatim source quotes (including comment indices), deterministic relevance/reason-code and polarity variation, pain points and unmet needs. Known matches require a supplied Known Insight sentence to occur in source text.
- Novelty judgments cover only requested new rows and vary from `none` through `very_high`.
- Running UI progress reads the API's existing top-level `tagCalls`, populated from worker `detail.tagCalls`. Call accounting now precedes pulse publication; fresh run detail is reset. Old stage reports cannot override live counts. Completed status uses `stage7.tag_calls`.
- Added pytest regressions for echo builders, static compatibility, live HTTP status, and a complete default-fake QA worker run; added a Vitest regression using the actual status wire shape, including absent/stale stage reports.

## QA method

The integration regression invokes `backend/tests/scripts/make_segment_qa.py <pytest-temp-dir> --confirm-all`, then POSTs `/evidence/{sid}/run`. It uses the real registry, default fake backend and embedder, durable work rows, `worker.execute`, pipeline, stores and HTTP endpoints. Only subprocess creation is replaced with an in-process worker thread, as in the existing integration harness. No evidence response or query-embedding overrides are used.

The existing QA backend on port 8320 was left running. No git staging or commits were performed. The pre-existing decision-log edits were preserved. Next build was intentionally skipped.

## Dataset limitation

The initial QA run produced no undifferentiated candidate. An exhaustive check of all edge documents within each of the ten Personas found no mutually similar three-document group at the required cosine threshold of 0.8. Thus this unchanged dataset does not allow that flag; the regression requires it when an eligible group exists. Synthetic fake labels exercise QA behavior and do not represent model-quality validation.

## Verification

- Full backend suite, once, including opt-in performance tests: `cd backend && .venv/bin/pytest -o addopts='' tests -q -s` — **1,988 passed, 1 failed, 2 warnings in 605.37 seconds**. The sole failure was the pre-existing no-attachment novelty example test. Fixed marker selection to retain static fixtures when no attachments are supplied.
- Post-fix targeted verification: `backend/.venv/bin/pytest backend/tests/llm/test_evidence_echo.py backend/tests/evidence/test_fixture.py::test_default_fake_backend_has_evidence_examples -q` — **8 passed, 1 warning in 3.50 seconds**. This includes all three original default-example cases and an additional exact-static-output regression. The full sweep was not repeated, honoring the requested single run; there is therefore no all-green full-suite run of the final revision.
- `npm --prefix frontend test`, once — **56 files, 540 tests passed**.
- `npm --prefix frontend run lint`, once — **passed**.
- `git diff --check` — **passed**.
- Backend warnings: existing Pydantic class-config deprecation and joblib physical-core detection fallback.

The full-suite QA integration regression passed with the following actual results:

| Metric | Result |
| --- | ---: |
| Input documents | 1,200 |
| Worker/status result | done |
| query_gen_fail | 0 |
| untagged | 0 |
| Contexts with at least one evidence item | 34 / 34 |
| tag_calls | 183 |
| Minimum Context coverage | 6 / 6 |
| Rare items across Context detail responses | 112 |
| Counter items across Context detail responses | 145 |
| Contexts with undifferentiated candidate | 0 |
| Personas whose edge vectors permit the required triple | 0 |

Logs: `/tmp/dcx-qa-fix1-backend.log`, `/tmp/dcx-qa-fix1-static-recheck.log`, `/tmp/dcx-qa-fix1-frontend.log`, `/tmp/dcx-qa-fix1-lint.log`.

## Remaining concerns

No known unresolved fix-specific failure. The single full backend run predates the final static-example compatibility correction, which was verified by targeted tests. Undifferentiated-candidate QA coverage remains limited by the unchanged synthetic vectors; no thresholds or fixture data were changed to force a flag.
