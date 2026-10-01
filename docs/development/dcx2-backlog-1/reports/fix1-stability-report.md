Status: COMPLETE

# Fix round 1 — stability report

## Changes

1. Moved vote-lease callback registration into `judge.run_worker`, immediately after cache creation and after the context-change existence check. Removed premature cache creation from `worker._judge`. Callback cleanup now also covers judge initialization failures. A regression test calls the real judge through `worker._judge`, verifies the Korean context-change notice, invokes the registered callback, and checks cleanup.
2. Removed lease refreshes from cooperative checkpoints, including the 100ms paused loop. Only the existing `HEARTBEAT_INTERVAL` background pulse refreshes leases, retaining the active-state and PID checks. The paused-loop regression observes one refresh from one explicit pulse across 20 polls. Existing pending-only, owner-only, expiry, and retry tests pass.
3. Starting a new monitor stores `training.monitor = None` together with its new `monitorRunId`. Using null replaces the old dictionary despite deep merging. A real inference/status regression proves a new `ValueError` reason is visible and old sample metadata is absent.
4. After version activation commits, failures stopping old-version workers are logged with the exception type and do not fail version creation. The API regression verifies HTTP 201, the active/read-only metadata, and sanitized logging. Failed cleanup can leave the old worker paused, as allowed by the brief's log-and-continue policy.
5. Document indexing parses outside write transactions and inserts at most 10,000 rows per transaction. File stamps are committed only after the whole file completes. Tests verify another writer can acquire the DB between transactions, identical public document projection/counts, warm no-op behavior, and replay after a malformed trailing row. Earlier batches remain committed on interruption; incomplete files are not marked complete and retry with idempotent replacements.

## Scope and ambiguity resolution

Only these source files were edited:

- `backend/app/work/worker.py`
- `backend/app/label/judge.py`
- `backend/app/model/infer.py`
- `backend/app/context/versions.py`
- `backend/app/label/overview.py` — indexing function only

Tests were changed/added only under the allowed paths:

- `backend/tests/label/test_judge.py`
- `backend/tests/label/test_lease_refresh.py`
- `backend/tests/label/test_index_batches.py`
- `backend/tests/label/perf_stability.py`
- `backend/tests/model/test_monitor_reason.py`
- `backend/tests/context/test_versions_backlog1.py`

The brief asks to extend the perf test but excludes `backend/tests/perf` from its editable list. The extension therefore lives in the allowed label-test directory as an opt-in pytest plugin. It instruments the existing perf test and adds a real fresh-interpreter, already-indexed measurement without editing the shared perf file. It verifies persisted file stamps and an initially empty estimate cache. Application imports happen before endpoint timing in the fresh process.

Inference does not lease judge votes, so no equivalent lease callback registration was needed there. `votes.py` required no changes. Review issue Minor #4 (monitor stop on its final sample) is not one of the controller brief's requested fixes and its source file is outside this job's ownership.

No changes were made by this job to `stale.py`, `sessions.py`, keyword/frontend files, or other jobs' tests. Their concurrent edits were preserved. No commit was made.

## RED — before production changes

Command from repository root:

```sh
backend/.venv/bin/python -m pytest \
  backend/tests/label/test_judge.py::test_worker_dispatch_preserves_context_notice_and_refresh \
  backend/tests/label/test_lease_refresh.py::test_paused_checkpoints_refresh_only_from_pulse \
  backend/tests/model/test_monitor_reason.py::test_new_monitor_clears_previous_reason \
  backend/tests/context/test_versions_backlog1.py::test_worker_stop_failure_does_not_fail_committed_version \
  backend/tests/label/test_index_batches.py -q
```

Recorded failure excerpts:

```text
context notice: assert any(...) -> assert False
paused polling: assert len(refreshes) == 1 -> assert 22 == 1
monitor reason: assert 'old reason' == '감시 중 오류가 났습니다(ValueError).'
version creation: sqlite3.OperationalError: sensitive detail
batch size: assert max(committed) <= 10001 -> assert 20004 <= 10001
interrupted indexing: sqlite3.OperationalError: no such table: document_files
```

Actual pytest failure summary:

```text
FAILED backend/tests/label/test_judge.py::test_worker_dispatch_preserves_context_notice_and_refresh
FAILED backend/tests/label/test_lease_refresh.py::test_paused_checkpoints_refresh_only_from_pulse
FAILED backend/tests/model/test_monitor_reason.py::test_new_monitor_clears_previous_reason
FAILED backend/tests/context/test_versions_backlog1.py::test_worker_stop_failure_does_not_fail_committed_version
FAILED backend/tests/label/test_index_batches.py::test_index_releases_writer_between_batches
FAILED backend/tests/label/test_index_batches.py::test_incomplete_index_is_not_stamped_and_can_retry
6 failed, 1 warning in 2.77s
```

The initial index fixture used an invalid collection ID; it was corrected to `c1` and all six failures above were reproduced before editing production code. The recorded RED output is from that corrected run.

## GREEN

Focused regression command:

```sh
backend/.venv/bin/python -m pytest backend/tests/label/test_judge.py backend/tests/label/test_lease_refresh.py backend/tests/model/test_monitor_reason.py backend/tests/context/test_versions_backlog1.py backend/tests/label/test_index_batches.py -q
```

```text
57 passed, 1 warning in 3.04s
```

Final required full-suite command:

```sh
backend/.venv/bin/python -m pytest backend/tests -q
```

```text
1395 passed, 1 deselected, 2 warnings in 141.08s (0:02:21)
```

An earlier full-suite run, while the parallel jobs were editing their files, reported 1393 passes and two failures: `test_legacy_full_save_still_overwrites` (extra completion data on a legacy session) and `test_unconnected_coverage_replaces_old_failure` (incomplete ProjectContext fixture). Both then passed in isolation on the updated files, and the final complete rerun above passed. This job did not edit either failing test or its implementation.

Warnings were the existing Pydantic class-config deprecation and joblib physical-core detection fallback. Scoped `git diff --check` passed. New tests use local fixtures/fakes; the suite guards external connections, and the perf fixture and fresh subprocess explicitly reject socket connections.

## Performance — 310,000 documents

Command from repository root (environment variables load the allowed-path extension):

```sh
PYTHONPATH=backend PYTEST_PLUGINS=tests.label.perf_stability backend/.venv/bin/python -m pytest backend/tests/perf -m perf -q -s
```

Final output:

```text
overview cold index=0.994730s estimate=11.708940s
overview documents=310000 cold=13.919198s
overview warm index=0.000385s estimate=0.000002s
overview documents=310000 warm=0.287060s
overview fresh-process indexed total=12.645054s index=0.000400s estimate=11.611451s
1 passed, 1 warning in 36.81s
```

| Case | Total | Index | Estimate |
| --- | ---: | ---: | ---: |
| Cold endpoint | 13.919198s | 0.994730s | 11.708940s |
| Warm endpoint | 0.287060s | 0.000385s | 0.000002s |
| Fresh process, persisted index | 12.645054s | 0.000400s | 11.611451s |

Warm latency passes the 0.5s target. Indexing releases the write lock between bounded batches. Estimate recomputation remains the dominant cold/fresh-process cost; changing the estimate cache is outside this brief. Timings are local observations, not cross-machine guarantees.
