# DCX 2.0 stage 7 — final fix round 2

**Status: Complete.** All requested fixes and verification passed.

Scope: `final-rereview1.md` N1, I3 remainder, all nine Minor findings (N2–N10), and all three test gaps. Changes are uncommitted on `feature/dcx2-stage7`.

## Fixes

| Finding | Resolution and evidence |
| --- | --- |
| N1 — stale disk package after refresh | `backend/app/evidence/pipeline.py:615` stages statement judgments in memory, rechecks the run, prompts and version writability, publishes selected evidence, and calls `_assemble` before releasing the session lock (`:649`). A successful refresh therefore publishes `package.json` synchronously. No dirty marker is produced. The targeted document/vector loader is retained. |
| N1 — version becomes read-only | No Context counts, KI pair cache, selected evidence or report is changed during remote judgment. If the final writable check fails, staged judgments are discarded. Regressions cover transition during judgment, already-read-only rejection, lock ownership during assembly, and reading the completed package from read-only history. |
| I3 — live tag count | D-268 was already correct: the running screen reads `status.tagCalls`. The existing Vitest checks both no `stage7` report and an inconsistent old report. Shared running fixtures now omit `stage7` and provide the real live field. |
| N2 — generation mismatch reported as failure | Publication mismatches bypass Context failure handling and set a Korean interrupted reason. `backend/app/work/worker.py:135` also preserves the interrupted state for evidence `stale_run` exceptions, so the public status endpoint does not override it back to failed. |
| N3 — overly broad generation comparison | `backend/app/evidence/generation.py:21` compares collection/preparation references, export reference, model ID, segment run and prompt hashes. Monitor/display changes do not discard completed Contexts. Existing full-dictionary snapshots are normalized for comparison; pre-snapshot runs preserve checkpoints under the normal stale/fresh guards. |
| N4 — sequential/duplicated refresh judgments | Refresh uses `settings.evidence_llm_concurrency`, with thread-safe call accounting. A separate version-level advisory refresh lock serializes overlapping refreshes across threads/processes; the second request sees published cache pairs. The session lock is released during LLM calls. A barrier-based test proves two batches execute concurrently and two overlapping refreshes make only those two calls. |
| N5 — GET publishes partial package | `backend/app/routers/evidence.py:188` no longer rebuilds packages. Running/incomplete requests return not-ready without changing the file, even if a legacy dirty marker exists. |
| N6 — prompt change has no usable recovery | Prompt mismatch returns Korean guidance to use “이어서 진행”. A completed screen with a request error exposes that action, respecting read-only/busy/prerequisite guards. |
| N7 — repeated body text | Body quotes replace the body preview; absent quotes render only the preview. Title/comment quotes retain the separate body preview. Existing Unicode and beyond-preview highlight tests remain green. |
| N8 — English worker collision | Launcher conflicts now explain in Korean that paused evidence also needs cancellation before restarting stage 6. Covered with an actual paused work row. |
| N9 — repeated KI requests | KI-number loading depends on session/version, explicit revision and run ID, rather than every status object. Polling with unchanged run no longer fetches KI again. |
| N10 — auto-start on completed evidence | `?start=1` is consumed once but starts work only for `none` or `stale`. Tests cover done, partial, interrupted and failed states as well as the existing running/read-only guards. |

The stale Persona-query fallback docstring noted in the review was also corrected; behavior was already correct.

## Regression coverage and TDD

- Added `backend/tests/evidence/test_rereview2.py` (12 tests) and frontend controller/card/recovery regressions before their corresponding fixes.
- Initial red runs: **10 backend failures** and **8 frontend failures**. The worker/public-status regression was added separately and failed with `failed` instead of `interrupted` before the worker fix.
- Rechecked the final disk-package test against HEAD's original refresh implementation in an isolated test-only override: it fails specifically because disk `tab` remains `["all", "new"]` after SQLite has excluded the document. The fixed implementation passes.
- The integration test now reads and validates `package.json` immediately after HTTP refresh, before any package GET, and checks `tab == ["all"]` and `novelty is None`.
- First stage-six completion explicitly requires evidence `none`; polling no longer accepts stale as an initial state.
- Focused checks passed: **60 backend tests** across round-two/pipeline/API/integration tests; the final expanded round-two file passed **12 tests**; frontend controller/screen tests passed **45 tests**.

## Final verification

The three requested final checks were each run once after implementation:

| Command | Result |
| --- | --- |
| `backend/.venv/bin/python -m pytest backend/tests -q -m ''` | **2002 passed**, 2 warnings, 575.40 s. Includes all three normally opt-in performance tests; no deselections. |
| `npm --prefix frontend test` | **56 files / 548 tests passed**, 2.77 s. |
| `npm --prefix frontend run lint` | **Passed**, exit 0, no lint diagnostics. |
| `git diff --check` | **Passed**. |

Backend warnings are the existing Pydantic class-based-config deprecation and joblib physical-core detection fallback. Neither is related to these fixes. Full-run logs: `/tmp/dcx2-full-backend.log`, `/tmp/dcx2-full-frontend.log`, `/tmp/dcx2-lint.log`.

## Concerns and boundaries

- Refresh still waits for its LLM batches and full package assembly. Calls are bounded and overlapping refreshes deduplicate, but provider latency means a fixed “few seconds” response time cannot be guaranteed. Synchronous assembly is intentional for the stage-8 file-reader contract.
- A pre-snapshot generation has no historical prompt/input fingerprint to compare; its first resume retains completed Contexts using the existing upstream-stale and explicit-fresh guards, then writes the new snapshot.
- Stage-8 strict nullable-field parsing remains the previously deferred D-259/T17 work; no stage-8 files were changed.
- No `next build`, `git add`, or commit was run. The QA backend on port 8320 was not stopped or restarted.
