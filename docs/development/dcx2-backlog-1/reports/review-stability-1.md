### Spec Compliance

- ✅ **T5 / AC-01**: `backend/app/routers/training_v2.py:67-71`. The reason is chosen in this order: the run's detail reason, then the saved `training.monitor.reason`, then "감시 중 오류가 났습니다(<종류>).", then "감시를 완료하지 못했습니다." for a failed or interrupted run. The reason is never overwritten with null.
- ✅ **T6 / AC-02**: `votes.py:89-93`. `refresh` only updates rows where `run_id=?` and `status='pending'`. `worker.py:51-53,66-67` calls it only when the heartbeat row update actually matched (`rowcount`), so it requires the same pid and an active state. Each refresh opens its own connection, so the background pulse thread is safe. The 600s rule in `reclaim` and the dead-owner fencing are unchanged. A dead process cannot refresh, and the test shows a lease is still reclaimed 601s after the last heartbeat (`test_lease_refresh.py:88-92`).
- ⚠️ **T6 wiring**: the callback is registered in `worker._judge` (`worker.py:83-95`) rather than inside the judge itself. This causes a regression (Important #1 below).
- ✅ **T7 / AC-03, AC-05**: `versions.py:73-74` leaves `monitor` out of `_idle`. `versions.py:77-91` runs in a single runs-DB transaction after `meta.json` is written and outside the rollback `try` (`:200-201`). It is still inside `locked(sid)`. The lock order is session lock, then runs DB. Workers' `heartbeat` and `_pulse` take only the runs DB, and the monitor releases the session lock before it calls `heartbeat`, so there is no lock inversion. A paused worker in the `heartbeat` loop sees `interrupted`, returns, and then `should_stop()` is true, so it stops polling. The final update in `execute` only applies to running or paused runs, so it keeps `interrupted`. Finished runs are untouched (tested). Running judge, prep, train or infer runs still return 409 (tested).
- ✅ **T8 / AC-04**: `store.py:30-34` checks the columns with `PRAGMA` and runs `ALTER ... DEFAULT 'auto'` inside the `BEGIN IMMEDIATE` init transaction. That is safe if two stores open at once, can be repeated, and turns legacy rows into `auto`. In `audit.py:69-74`, the schedule counts only `auto` rounds, round numbers stay global MAX+1, and an unknown kind raises an error. `labeling_v2.py:206` passes the real count with `kind='manual'`. Tests cover the 500-manual, 1000-auto and 11000-auto sequence and the legacy case of round 7 going to round 8.
- ✅ **T9 / AC-06**: `pytest.ini` has `addopts = -m "not perf"` and registers the marker. Running with an explicit `-m perf` replaces that default. The default suite is unchanged (1 deselected), and warm time is 0.284s against a 0.5s target. No change was made to `overview.py`, which is correct.
- ✅ **Stage 0-2 crawl**: the crawl workers use their own registry (`app/crawl/control.py`) and never import `app.work.worker`, so these changes do not affect them.

### Issues

**Important**

1. **Production judge runs lose the "context changed" notice.** In `worker.py:89`, `_judge` calls `VoteCache(root)` before `judge.run_worker` runs. Creating the cache creates `votes.sqlite`. `judge.py:96` then computes `changed = not (root/'votes.sqlite').exists() and ...`, which is now always False.
   - Scenario: the user edits the one-liner and restarts judging. Previously they saw "판정 맥락이 바뀌어 다시 판정합니다". Now that message never appears.
   - Why tests miss it: `test_judge.py:92` calls `judge.run_worker` directly and skips `_judge`.
   - Fix: register `ctx._heartbeat_callback` inside `judge.run_worker` after `cache = VoteCache(root)` (`judge.py:97`). This also removes the duplicate session read and root calculation, and puts the callback after the labeler check.
   - Add a test that goes through `worker._judge` or `execute`.

**Minor**

2. **A refresh every 100ms while paused.** In the paused `heartbeat` loop (`worker.py:56-70`), every 0.1s iteration matches a row and calls `refresh`, which opens a `BEGIN IMMEDIATE` write on `votes.sqlite`. That cache is shared across versions. A paused judge therefore takes the write lock about 10 times a second for as long as it is paused. It also keeps its pending leases alive indefinitely. T7 only clears paused workers on the old active version.
   - Fix: refresh only from `_pulse`, or limit it to once per `HEARTBEAT_INTERVAL`.
3. **A stale saved reason can hide a new monitor's error.** `training.monitor` is deep-merged and never reset when `infer.py:223` starts a new monitor. If a second monitor fails with an exception, status shows the first run's saved reason (for example "감시 표본 2건…") instead of "감시 중 오류가 났습니다(X)". This follows the spec's priority order, but it is wrong in this case. Fix: clear `training.monitor` when setting `monitorRunId`.
4. **A monitor stopped on its last sample ends as `failed`, not `interrupted`.** If the stop arrives after the sampling loop, the final `session(..., writable=True)` (`monitor.py:125`) hits the now read-only version and raises `StoreError`. The run is recorded as `failed` with the reason "감시 중 오류가 났습니다(StoreError)." This is cosmetic.
5. **A 500 can be returned after the version was already created.** If `_stop_readonly_workers` fails (for example a busy runs DB past its 30s timeout), the new version is already active and the paused workers were not stopped. Consider catching and logging the error, or retrying.

### Is the 14.8s cold first call a real problem?

Yes, a moderate one, and I'd raise a low-priority follow-up. The cold cost comes from two places:

- **`index_documents`**: this happens once per prep. The result is stored in the database, keyed by a file stamp. It inserts 310k rows inside a single `BEGIN IMMEDIATE` on `labels.sqlite`. For about 10 seconds or more, every other writer is blocked (human submits, judge `sync`, audit) against a 30s timeout. On a slower Mac mini, or with longer documents, that can turn into "database is locked" failures, not just a spinner.
- **The `_estimate` cache**: it lives only in process memory, so a cache miss reloads all 310k documents after every backend restart. During active judging the estimate comes from the worker's detail, so the steady state is fine.

Recommended follow-up:
- Measure the two parts separately, including a "second process, already indexed" case.
- Index in batches with short transactions, or run indexing in the prep worker instead of the GET request.

### Assessment

The concurrency, ordering, migration and perf-marker work is correct, and the tests are thorough. Issue #1 is a real behaviour regression that the tests miss, and it is a small change to fix. #2 is a cheap fix worth doing at the same time.

Task quality: Needs fixes
