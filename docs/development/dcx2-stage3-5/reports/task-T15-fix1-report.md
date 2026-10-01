# T15 fix round 1 report

## Scope and outcome

Implemented all five findings in `task-T15-fix1.md`. Read the fix brief, the review's final assessment, and the original T15 brief before implementation.

Only these backend files were edited:

- `backend/app/context/store.py`
- `backend/app/context/versions.py`
- `backend/app/work/runner.py` (status read helper only)
- `backend/tests/context/test_versions_stage3_5.py`
- `backend/tests/context/test_t15_fix1.py` (new regression tests)

This report is the requested documentation output. No frontend files were edited by this task; concurrent frontend changes in the worktree were left intact. No packages were installed and no commit was created.

## Changes and verification coverage

1. **Activity badges clear after replacement or a version change.** `runner.status()` includes version and labeler in its status projection and orders rows by start time, with insertion order breaking ties. `session_activities()` uses the session metadata's active version and selects the latest run per `(kind, labeler)` before filtering for badge states. A completed replacement suppresses an older interrupted/failed run. Tests use persisted run rows, cover both judge and train, insert rows out of chronological order, check distinct labelers/kinds, check old-version exclusion even when a caller supplies old session data, and verify the `/sessions` response.

2. **Restarted versions do not expose copied stage reports.** Restarts at stage 5 or earlier remove the new version's `stage_5.json`; restarts at stage 3 or earlier also remove `stage_3.json`. Original-version files remain intact. Comparison does not fall back to a shared preparation report while preparation is stale; once preparation completes, reuse of the shared report works again. Tests cover restarts at every stage from 0 through 5, training status, comparison returning `same=False`, original-file preservation, and monitor completion not republishing a stale report. Monitor dependencies use an empty offline document set and the real prediction schema to exercise its report-publication branch.

3. **SQLite snapshot test now includes an actual commit during backup.** Retained the existing after-backup boundary case and added a parametrized during-backup case. The SQLite connection subclass runs the real backup API with `pages=1`; its progress callback asserts pages remain, signals a separate submitting thread, and waits for that thread's `LabelStore.submit()` commit before copying resumes. Both cases check `PRAGMA integrity_check == 'ok'`, snapshot row counts and document membership; any included submitted row must exactly match the committed source row. The source must contain both rows. This was a coverage gap, so the existing production backup implementation needed no change.

4. **Session listing does not create missing worker databases.** `runner.status()` returns an empty list before opening a transaction when `runs.sqlite` does not exist. The `/sessions` regression checks that neither the database nor its session work directory is created. Existing databases retain heartbeat refresh behavior.

5. **Stage-3 comparison includes both reports.** The response now contains `stage_3` and `stage_5` before/after figures, with `same` calculated across both. Stage-4/5 comparison responses retain their existing shape.

## TDD and validation

- Before changing production code, ran `backend/.venv/bin/python -m pytest backend/tests/context/test_t15_fix1.py -q`: **14 failed, 1 passed**. Failures reproduced superseded badges, old-version badges, missing-database creation, copied reports, stale preparation fallback, and missing stage-5 figures in stage-3 comparison.
- The added concurrent-backup case initially contained an incorrect test assumption that `LabelStore.submit()` also writes `final`. Source inspection showed it appends only to `human`; corrected the assertion to compare the full committed human row. Both backup cases then passed on the unchanged backup implementation. This fixture error is not counted as a production RED result.
- The first context/work run reached **119 passed, 6 failed**; all six failures were the new monitor fixture missing `model_predictions`. Initialized that fixture through the real `infer.prediction_schema()` helper, without production changes.
- Focused final command: `backend/.venv/bin/python -m pytest backend/tests/context/test_t15_fix1.py backend/tests/context/test_versions_stage3_5.py -q`: **32 passed**, one existing Pydantic class-config deprecation warning.
- Full required command from repository root: `backend/.venv/bin/python -m pytest backend/tests -q`: **1184 passed, 2 warnings in 118.05 seconds**, exit code 0. This includes the existing stage 3–5 integration and worker tests. Warnings were the Pydantic class-config deprecation and joblib falling back to logical CPU count after physical-core detection failed.
- `git diff --check` for the permitted backend changes passed.

## Deliberately unchanged

The fix brief's parked items remain unchanged: failed/interrupted wording, the read-only WAL-without-SHM edge case, and monitor work blocking version creation. Status reads for existing worker databases still refresh interrupted workers through the existing transaction path; only the absent-database path avoids all worker database writes. Historical run rows are preserved.
