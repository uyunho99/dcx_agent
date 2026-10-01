Verdict: **Needs fixes.** All 8 brief items are addressed. One new Important issue: the cluster fix leaves any version restarted from stage 6 or earlier unable to ever show clustering as done.

**Coverage brief (rfix-coverage)**

1. **Heartbeat during fetch: Addressed.**
   - `naver_autocomplete.py:61-91`: `on_progress` is called after every seed, whether it succeeded or failed. It sits outside the seed's try block, so a superseded-job error stops the next request.
   - `rounds.py:410-428`: the 30s heartbeat now starts before the SearchAd/autocomplete fetch and stops in `finally` (around line 466). The heartbeat holds no lock while waiting, so `join` cannot deadlock.
   - Ownership: `progress()` (lines 411-417) checks for raw `loading` plus the same `startedAt`, so a superseded job cannot be revived. A worker that is still alive can push a stale (over 2 min) record back to `loading`. That is by design and matches the existing `finish()` behaviour.
   - The test for 21 seeds × 9s holds.
2. **R3 409 gate: Addressed.**
   - `rounds.py:117-119`: the 409 message is exactly `'커버리지를 받는 중입니다. 끝나면 R3를 만들 수 있습니다.'`. It is checked inside `_CheckedPatch.items()`, which runs under the `update_session` lock that admits the round.
   - Line 140 stores `coverageSnapshot` in that same patch, and `_inputs` reads it (lines 192-194).
   - Status `unavailable` still allows R3, including stale `loading`, which the projection turns into `unavailable`. `connected` and `unconnected` also allow it. Both regenerate and start are tested.
3. **`previous` split: Addressed.**
   - `rounds.py:386-394`: the active fields are cleared and moved into `previous`.
   - Recompute only runs when `humanQueries` is in the saved record (line 381) and never reads `previous`. On a stale refresh, R2 re-commit hits the `interrupted` branch and shows `unavailable`.
   - The terminal value drops `previous` on finish.

**Completion brief (rfix-completion)**

1. **clustersDone: Addressed as specified.** At `sessions.py:46-52` it now needs the cluster job's status to be `done` and no `stage6` stale marker. Error jobs, running jobs and partial files give false, and the tests cover v1/v2 and stage3/stage6 restarts.
2. **judge_done reconciliation: Addressed.**
   - `stale.py:50-75`: there is a lock-free early exit when nothing is pending or the run database is missing. The run database is opened read-only, everything is wrapped in a catch-all (fail-soft), and the session file is reread under the lock before a write that happens only if needed (idempotent; the test checks exactly one write).
   - Replaying a run that is already done now repairs it (lines 85-90).
   - Lock order is the session lock then the run database, same as in `judge_done`. `get_session` reads `data` before taking the lock (`sessions.py:105-106`), so it cannot deadlock.

**Frontend:** it still builds and renders. If a user races the 409, the message shows: `request()` throws `KeywordApiError` with the server message, and `action()` passes it through `reportError` → `displayError` (it contains Hangul, so it is shown verbatim). `page.tsx:108` also blocks this on the client side.

**New issues**

Critical: none.

Important:
- **I1: clustering can never complete in a restarted version.** `versions.py:183-185` marks `stage6` stale for every restart from stage 6 or earlier. Nothing in `backend/app` ever clears `stage6`: `clear_stale` is only called for `stage3` (`prep/pipeline.py:141`) and `stage5` (`model/export.py:98`). So `clustersDone` stays false even after clustering is re-run successfully in that version, and `completedThrough` never reaches 6 there. Fix: clear `stage6` when the clustering job publishes `done`, or tie the cluster job to the version it ran for.

Minor:
- **M1:** `clustersDone` reads in-memory `job_manager` state, so it goes false after a backend restart. Files no longer count, so this is a regression from before.
- **M2:** The cluster job is session-scoped, so a cluster run done in v2 also shows `clustersDone=true` on a readonly v1 that has no `stage6` marker.
- **M3:** The R3 gate (`rounds.py:118`) runs before the running-job early return (line 122). A repeat POST while R3 is running and coverage has since gone to `loading` now gets 409 instead of the existing job.
- **M4:** The `loading` record no longer has `source`, so `CoveragePanel.tsx:6` always shows the autocomplete "(약 20초)" text, even for SearchAd. The metrics card dims empty values, since `previous` isn't read. The brief allowed this, but the UI looks worse.
- **M5:** A non-superseded write error inside `on_progress` aborts the whole fetch, and the run lands as `failed`.
- **M6:** `reconcile_judge_done` can write into a readonly version's `session.json` through `?version=`, bypassing `assert_writable`. It also takes the lock on every read while labeling is not done. Both are acceptable but worth noting.

Verdict: Needs fixes
