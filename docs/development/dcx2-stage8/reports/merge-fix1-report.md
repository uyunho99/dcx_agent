# Merge fix 1 — D-320 and merge-review1

## Changes

- **I1 / D-320:** Added `evidence_ready(sid, version)` with the single rule `evidence.status == 'done' and 'stage7' not in stale`. Persona start/retry, status `package`/`evidence_required`, stale detection, worker source checks, and computed `personaDone` use it. Rejected launches retain HTTP 409, `evidence_required`, and the existing Korean copy. Insight publication checks also reject evidence that is no longer ready.
- **M1:** Producer validation errors become `PackageInvalid(PackageMissing)`, so invalid JSON/contracts follow the existing safe API handling instead of HTTP 500. Corrected the strict producer-contract docstring and exception assertions.
- **M2:** Removed the unreachable package `projectContext` fallback from concept generation; session context remains the source.
- **M3:** Missing insight ODI remains null, renders as `—`, and has no rectangle. Measured zero remains zero, including historical views.
- **M4:** Null-quote persona traces show `인용 없음 · 추론` and the `인용 미확인` warning instead of empty location fields.
- **M5:** The worker registration transaction now excludes overlapping segment/evidence/persona/insight jobs within a version. Concurrent launch tests check that exactly one job starts.
- **M6:** Extended the real stage-7 contract test through HTTP persona and insight derive launches, the real runner/worker dispatch, and durable output using fake LLMs. Only the subprocess boundary is replaced by an in-process worker thread; network access is blocked.

## Regression and TDD evidence

Tests were added and executed before the corresponding production changes:

- Readiness: partial, running/resumed evidence, and stage7-stale states reject start/retry and report `package=False`; retained identical package/confirmed identities cannot restore `personaDone` or current persona status. The segment reset regression deliberately preserves the evidence generation metadata to isolate readiness from digest/run changes, then re-confirms identical persona/context values.
- Invalid package: extra legacy `projectContext` key formerly raised uncaught validation errors; run now returns the Korean 409 contract, while status/cards remain readable.
- Dead fallback: the corrected regression observed the obsolete package goal instead of the empty session goal before removal.
- UI: null ODI and null-quote trace tests each failed before the rendering changes.
- Launch guard: all four concurrent kind-pair cases failed before expanding the shared conflict set.
- Real producer contract: both workers completed, then the new resumed-evidence assertion failed with HTTP 200 before the readiness fix.
- Additional lifecycle coverage executes an actual evidence skip that leaves another Context pending, and probes persona launch during an actual non-fresh evidence resume with the old package still present.

Red logs: `/private/tmp/mergefix-red-backend.log`, `mergefix-red-identical.log`, `mergefix-red-concepts.log`, `mergefix-red-contract.log`, and `mergefix-red-frontend.log`.

## Validation

- Focused backend verification: **83 passed**.
- Full backend suite, `cd backend && .venv/bin/pytest`: **2,332 passed, 3 deselected, 2 warnings**, exit 0, 385.21 seconds. Run once; the repository default `-m "not perf"` excludes the three opt-in performance tests.
- `npm --prefix frontend test`: **693 passed in 64 files**.
- `npm --prefix frontend run lint`: **passed**, no diagnostics.
- `git diff --check`: passed.

Full-run logs: `/private/tmp/mergefix-full-backend.log`, `/private/tmp/mergefix-full-frontend.log`, `/private/tmp/mergefix-lint.log`.

## Scope and concerns

No build was run. No git add or commit was performed. The QA server on port 8321 was not stopped. Pre-existing decision-log and merge-review changes were preserved. No subagents were used.

No known functional concerns after all requested checks. Backend warnings are the existing Pydantic class-config deprecation and joblib physical-core detection fallback. The three opt-in performance tests were excluded by the repository default. The full backend suite, full frontend suite, and lint were each run once after the fixes; focused red/green runs are listed separately above.
