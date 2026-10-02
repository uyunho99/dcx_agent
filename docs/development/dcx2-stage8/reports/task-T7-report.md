# T7 report — persona worker, versions, completion

Status: implemented and verified. No git add/commit; no subagents used.

## Changes

- Added `backend/app/persona/pipeline.py`: package load → Persona card → grade → prescription/constraint → scope → opportunity map/tree → PersonaStore publication of cards/map/tree/stage_8 → session publication.
- Persona-unit durable cards and `checkpoint.json`; resume rotates the public run UUID and skips successful Personas. Failed units remain retryable. Durable cards recover a crash between cards and checkpoint replacement.
- A failed card, prescription (including PrescriptionError), or scope affects only that Persona and exposes the exact message `이 페르소나 카드를 만들지 못했습니다.`. Other Personas continue; retries preserve completed cards.
- Counts LLM task results/calls through `_Calls`, with cooperative heartbeat/stop boundaries before calls and around Persona publication. All backend/timeout outcomes interrupt the run using the stage-six `LLM_REASON` verbatim; the BaseException signal also makes the shared worker record interrupted.
- Detects changed package run/content and stage-six confirmed identity, Desire, Goal, Context name/action. Checks before generation and before publication; changes mark stage8/persona/insight stale. Fresh regeneration accepts a refreshed package but rejects a package that disagrees with confirmed stage-six values.
- Added worker KINDS `persona` adapter.
- Existing restart artifact rules retained: stage8 deletes only persona; stage7 additionally deletes evidence; stage6 additionally deletes segment. Restarts now remove completion.personaDone and completion.insightDone.
- Added compare(stage8) report, Persona status, insight/concept revision/count summaries and full artifact hashes, including report-only/content-only differences and absent artifacts without creating directories.
- `_completion` computes personaDone from status done and absence of stage8 stale, and insightDone from selected-version insights.json revision >= 1 and absence of stage8/stage9 stale. Completion reads remain read-only.
- Updated four exact-dictionary expectations in existing `backend/tests/context/test_session_completion.py` for the two newly required completion keys (12 parametrized cases). This was the only additional existing test file changed.

## Public integration contract for T10/T11

- `run(context)` args: `{fresh?: bool, personas?: list[str], run?: str}`. `run` is the public Persona run UUID, not the supervisor's context.run_id.
- `assert_run(sid, version, run_id)` is a read-only guard, safe inside a router-held session lock. It raises StoreError(status=409, kind='stale_run') for obsolete/missing publication IDs. Call before queuing retry to return an immediate HTTP 409; the worker also checks supplied args.run before mutating artifacts.
- `mark_stale_if_changed(sid, version)` reconciles already-published cards against current upstream input. Call outside a session lock because it can publish stale state. Worker entry and publication checks already enforce this internally; a status/read endpoint can use the helper to detect edits before another run.
- PersonaStore mutation methods are always called without an outer session lock.
- Cards format: `{run, package_run, package_hash, personas: {id: {status, card, grades, summary, traceable_support, trace, prescription, constraint, scope}}}`; failed rows contain status/error; unprocessed selected-run rows remain pending. A subset run does not mark unprocessed Personas complete.
- stage_8 report fields: `run`, `at`, `cards` (successful), `failed`, `grades` (observed/inferred/speculated), `null_attributes`, `constraint_violations` (final verdicts), `represcribed`, `blocked`, `future`, `zones`, `stars`, `insights`, `above_mean` (including equality), `concepts`, `chat_revisions`, `llm_calls` (task suffix counts), `params`, `provisional`.
- Downstream counts reflect durable insights/concepts at Persona report publication. T10's insight/edit worker owns refreshing those report fields after later downstream mutations.

## TDD and validation

1. Wrote `backend/tests/persona/test_pipeline.py` and `backend/tests/context/test_versions_stage8.py` before implementation.
2. RED: targeted pytest command exited 2 because `app.persona.pipeline` did not yet exist.
3. Implemented and refined report/fake-runner behavior; targeted command passed: **25 passed**. Cases include resume, card/prescription/scope isolation and retry, backend/timeout/raised timeout interruption, package changes, name/Desire/Goal/action-only changes, stale UUID 409, mid-call source change, schema failures, fresh reset, selected units, report fields/downstream counters, version reset/comparison and completion.
4. Ran the exact requested `backend/.venv/bin/python -m pytest backend/tests/persona backend/tests/context -q` once. Collection failed because both directories have a non-package `test_store.py` module. `--import-mode=importlib` alone also exposed existing bare `from test_api import ...` imports in context tests.
5. No collection configuration or unrelated test imports were edited. Used:
   `PYTHONPATH=backend/tests/context:backend backend/.venv/bin/python -m pytest backend/tests/persona backend/tests/context -q --import-mode=importlib`
   Initial execution exposed the 12 old completion-key expectations described above. After the narrow expected-value update, final result: **403 passed, 2 warnings in 9.54s**.
6. Ran the exact requested `backend/.venv/bin/python -m pytest backend/tests/segment -q` once: **214 passed, 1 deselected, 2 warnings in 133.06s**.
7. `git diff --check`: passed.

## Concerns / handoff

- The literal combined persona/context command still needs the documented import-mode/PYTHONPATH workaround; the default collection collision predates these changes.
- Existing warnings: Pydantic class-config deprecation and joblib physical-core detection fallback. No test failures remain with the documented test invocation.
- T11 must use assert_run before queuing a retry for an immediate HTTP 409, and may use mark_stale_if_changed on status reads. T10 must refresh downstream stage_8 counters after insight/concept edits.
- Parallel changes to insights/radar/concepts, prescribe and associated tests/prompts, frontend files and decision log were left untouched by T7.

## Completion check + collision fix

- Re-read the T7 brief and report, reviewed the tracked diff and new pipeline/version test files, and checked the stage_8 report against design §5.10. No additional T7 implementation gaps found: generation/publication, resume, isolated failures and retry, total backend interruption, upstream package and confirmed identity staleness, stale-run 409, report fields, stage 6/7/8 restart cleanup, stage8 comparison, and selected-version completion are covered.
- Reproduced the default full-suite collection failure before editing: two import-file-mismatch errors involving persona/context `test_store.py` and persona/prep `test_pipeline.py`.
- Added `backend/tests/persona/__init__.py`, following the existing segment test-package convention. No test import changes or additional package markers were needed. Default collection now succeeds: **1910/1912 tests collected (2 deselected)**. This supersedes the earlier report's collection concern and import-mode/PYTHONPATH workaround.
- Ran the full backend suite exactly once with `backend/.venv/bin/python -m pytest backend/tests -q`: **1910 passed, 2 deselected, 2 warnings in 282.97s (0:04:42)**, exit code 0. This also verifies the existing persona test helper imports under default collection.
- `git diff --check` passed. No frontend files touched; no git add/commit or subagents used.
- Concerns: no T7 blockers found. The two existing warnings remain (Pydantic class-config deprecation and joblib physical-core detection fallback). The T10/T11 integration responsibilities documented above remain applicable.
