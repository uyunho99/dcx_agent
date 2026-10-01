Scoped re-review of the rfix2 diff (last two commits: 9386c30 clustering/stale, f049e80 rounds). I read the code and the new tests but did not run the suite. The 1447 backend passes come from your verification.

**Cluster brief (rfix2-cluster.md)**

1. **Persist done and clear stage6: Addressed.**
   - `backend/app/services/clustering.py` (the new block after the `save_jsonl` loop) runs under `store.locked(sid)`.
   - It calls `store.assert_writable(sid, run_version)` and writes `clustering={status:'done', version, at}` through `_update_locked`.
   - It then calls `clear_stale(..., 'stage6', already_locked=True)`.
   - `run_version` is taken from the session inside the first lock (`assert_writable(sid)` then `session['version']`).
   - If the active version changed during the run, `assert_writable` raises, the job ends in error, and nothing is marked. Covered by `test_cluster_cannot_complete_a_different_active_version`.
   - `/save-session` can't overwrite the field: `clustering` was added to the `owned` set in `backend/app/routers/sessions.py` (line ~89).
   - A failed publication leaves stale untouched (`test_failed_cluster_publication_preserves_stale`).
2. **clustersDone reads only the persisted field: Addressed.**
   - `sessions.py` `clusters_done()` is now `stage6 not stale and data['clustering'].status == 'done'`.
   - There is no `job_manager` or file read.
   - The restart test swaps in a fresh `JobManager` and still sees done.
   - It also checks that v1 stays not-done and that v1's `session.json` is byte-identical after the v2 run.
3. **Readonly versions are never written by reconcile: Addressed.**
   - `backend/app/context/stale.py` (~line 68) calls `store.assert_writable(sid, selected)` inside the lock, before `_publish_judges`.
   - A readonly or non-active version raises, and the surrounding `except Exception` swallows it.
   - `test_reconcile_judge_done_skips_readonly_version` is parametrized on an explicit version.

**Coverage brief (rfix2-coverage.md)**

- **M4, source in the loading record: Addressed.** `rounds.py:393-394` sets `'source'` to `searchad` when all three SEARCHAD credentials are configured (same check as `naver_searchad.py:34`), else `autocomplete`. Progress writes use `{**saved, **values}`, so the source persists. `test_review2_loading_source_matches_credentials` covers it.
- **M3, ordering: Addressed.** In `start_round`, the running-job early return now comes before the R3 coverage-loading 409 gate. The test is parametrized on `regenerate`.
- **M5, storage error in the progress callback: Addressed.**
  - `rounds.py` (~line 420) re-raises `_JobSuperseded` and logs-and-continues on any other exception.
  - Tests: `test_review2_progress_write_error_does_not_abort_fetch` and `test_review2_progress_supersession_still_stops_fetch`.
  - The heartbeat thread still stops on any error. That is the pre-existing behavior and is acceptable.

**Stage 0-2 and legacy sessions: still works.**
- Legacy sessions (no `schemaVersion`) take the unchanged `else` branch with `run_version=None`. There is no persistence and no lock, and the job_manager done/error path is unchanged.
- `get_session` skips `completion` for legacy sessions, so removing the job_manager read doesn't affect them.
- `test_integration_stage0_2` and the other legacy tests are in the passing suite.

**New issues**

- **Critical:** none.
- **Important:** none.
- **Minor:**
  1. `clustering.py` uses `session['version']`, a hard KeyError if a schema-v2 session lacks `version`. This is unlikely, since `_update_locked` always sets it. `.get('version')` would be safer.
  2. `clusters_done()` doesn't compare `clustering.version` to the selected version. It relies on `stage6` stale being set when a version is forked. If a fork is ever created without marking stage6 stale, the copied `clustering` would read as done. Checking `version == selected` is cheap insurance.
  3. `versions._restart` doesn't clear the inherited `clustering` field. This is harmless today because of the stage6 stale marker.

Verdict: Approved
