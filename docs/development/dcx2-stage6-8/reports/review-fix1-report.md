# DCX 2.0 stage 6 bundle 1 — review fix wave 1

Worktree: `/Users/persona1/Desktop/dcx_agent-stage6-8` (`feature/dcx2-stage6-8`). All four review findings addressed. No staging, commits, subagents, or reviewers. Existing untracked review/build artifacts were left unchanged.

## 1. Nullable export probabilities

- `backend/app/segment/dims.py:162`: normalize nullable export mappings.
- `backend/app/segment/dims.py:235`: normalize nested nullable probability/semantic mappings, count unavailable Act values as `act_unknown`, and exclude them from `act_mismatch`. Include the unknown count in both context and overall summaries (`:304`).
- Searched all `backend/app/segment/` references to `tagProbs` and `pred_entropy`. `signals.py` already passes missing/null entropy through without numerical operations; no extra production guards were necessary.
- `backend/tests/segment/test_dims.py:215`: synthetic Core sample with null probabilities, nested null mappings, and null entropy; verifies unknown/mismatch counts and cache resume.
- `backend/tests/segment/test_pipeline.py:365`: full synthetic pipeline with alternating null probability/entropy exports, pause after quality, resume through dimensions, and a second resume. Confirms null entropy survives on Core rows.
- **RED:** the new dimension test raised `AttributeError: 'NoneType' object has no attribute 'get'` before implementation.
- **GREEN:** dimension regression passed in the segment/context suite. Additional full synthetic resume regression: **1 passed**, 4.48 s.

## 2. Generation/rows read consistency

- `backend/app/routers/segment.py:83`: request-local `ConfirmationStore.snapshot()` opens a read transaction with `BEGIN`, reads `meta.run`, and pins subsequent store reads to that same connection until response data is collected.
- `backend/app/routers/segment.py:214`, `:222`, `:243`, `:307`: clusters, personas, contexts, and docs use the snapshot. Layer gates, document/author aggregates, and paginated document totals also share it. Original document text loading occurs after the SQLite snapshot closes.
- `backend/tests/segment/test_api.py:392`: a second SQLite connection replaces the generation and rows between the generation read and row reads, parameterized across all four endpoints.
- `backend/tests/segment/test_api.py:421`: resets after Persona rows are read, reproducing the originally reported old-rows/new-generation response.
- **RED:** corrected interleaving tests produced **4 failed, 1 passed**: clusters, contexts, docs, and the Persona-after-rows regression failed with mixed generations. (An initial docs test lacked a preparation fixture; that was corrected before treating its assertion failure as evidence.)
- **GREEN:** all five interleavings passed; existing API confirmation/stale-run tests stayed green in the segment/context suite.

## 3. Stage-six version comparison

- `backend/app/context/versions.py:300`: explicit stage-six branch reads `segment/stage_6.json` and saved layer fields from the version-local SQLite database in read-only mode. Missing/reset results produce empty summaries without creating a database.
- Response includes report availability/summary, full-report content hash for detecting differences outside the displayed summary, saved cluster/persona/context names, Desire, Goals, Action, and confirmed/total counts. Confirmation timestamps themselves do not affect equality. Per-document coverage/code/context detail is omitted from the report summary. Stages 0–5 retain their existing branches.
- `frontend/src/app/pipeline/compare/page.tsx:42`, `:68`: renders stage-six summaries in labeled version columns, with report absence, saved fields, and confirmation counts instead of treating them as timestamped files.
- `backend/tests/context/test_versions_stage6.py:145`: copied equality, changed confirmations, changed report, and completed-versus-reset comparison, including no filesystem creation during reset comparison.
- `frontend/src/app/pipeline/compare/page.test.ts:12`: renders report absence and every requested saved field/count; rejects `Invalid Date` output.
- **RED:** backend comparison incorrectly returned `same: true` after saved fields changed. Frontend regression failed because `Bedroom` was absent and the generic file renderer emitted `Invalid Date`.
- **GREEN:** backend comparison passed in the segment/context suite; frontend comparison passed with the clustering tests (**42 passed** at that checkpoint, before the additional autosave ordering test).

## 4. Debounced edits and navigation

- `frontend/src/components/segment/SegmentScreen.tsx:30`, `:79`: registers unsaved edits with the existing DirtyProvider, retains the pending draft in a ref, serializes saves, and flushes on cleanup even after the screen becomes inactive. Existing navigation consumers use DirtyProvider's `confirmNavigation`.
- `frontend/src/components/segment/SegmentScreen.tsx:104`: browser-unload warning while unsaved, plus cleanup flush and dirty registration removal.
- `frontend/src/components/segment/SegmentScreen.tsx:178`, `:208`, `:239`, `:304`: clear obsolete pending edits on generation change/successful confirmation/reset. Revision checks prevent an older completed save from clearing a newer edit's dirty state. Failed saves retain their pending draft and dirty protection.
- `frontend/src/app/pipeline/clustering/page.test.ts:258`, `:275`, `:288`: fake-timer tests for latest-edit flush within 600 ms, in-flight and failed-save dirty state, and overlapping-save ordering. Existing confirmation/remount/reset tests remain green.
- **RED:** both new initial autosave regressions failed because no dirty registration occurred (**2 failed, 39 passed**).
- **GREEN:** all clustering tests passed after implementation; after the ordering regression was added, **42 passed**. Unmount test verifies exactly one PATCH containing the latest edit, including after advancing past the original debounce deadline.

## Verification

- `backend/.venv/bin/python -m pytest backend/tests/segment backend/tests/context -q`: **402 passed, 1 deselected**, 141.08 s. The subsequently added full synthetic nullable-export/resume test separately passed and is also included in the final full suite.
- `backend/.venv/bin/python -m pytest backend/tests -q`: **1696 passed, 2 deselected, 2 warnings**, 281.66 s; exit code 0. Run once after implementation and targeted checks.
- `npm --prefix frontend test`: **432 passed, 52 test files**, 2.51 s.
- `npm --prefix frontend run lint`: **passed**, no lint findings.
- `npm --prefix frontend run build -- --webpack`: **passed**, TypeScript checks and all 14 static pages generated.
- `git diff --check`: **passed**.

## Concerns and limits

- No known remaining failure from the four findings. An in-app navigation flush uses the existing asynchronous PATCH; a browser/process termination or network failure cannot guarantee persistence. Browser unload is guarded while unsaved, and failed mounted saves remain dirty.
- The SQLite snapshot covers generation, rows, gates, and row-derived totals. Session JSON and report JSON remain separate files; this change does not claim a cross-file transaction.
- Comparison detects full-report changes through a content hash while displaying a compact summary; detailed per-document changes are not expanded in the comparison UI.
- Existing runtime warnings: Pydantic class-based configuration deprecation, joblib physical-core detection fallback, and Node `module.register()` deprecation. No unrelated warning cleanup was attempted.
