Status: COMPLETE

Completed review findings #3 and #4 from `docs/development/dcx2-backlog-1/reports/codex-branch-review1.md`, per `rfix-completion.md` (R-207).

## Changes

- `backend/app/routers/sessions.py`: `clustersDone` requires cluster job status `done` and no selected-version `stale.stage6` marker. Removed file-existence fallback, so partial files cannot imply success. Stage-3 and stage-6 restarts suppress the inherited session-scoped job result.
- `backend/app/context/stale.py`: completed judge runs can replay publication. Session reads reconcile the latest version-local Jev/GPT terminal evidence under the session lock, reread session JSON before publication, clear only stage4, and set labeling status to done. Repeated recovery avoids duplicate writes. Recovery failures leave reads available and preserve durable run evidence for retry; missing databases are not created by reads.
- `backend/tests/context/test_session_completion.py`: updated the file-only completion expectation and added running/error/missing-job partial-file regressions plus selected/active restarted-version coverage.
- `backend/tests/context/test_stale_clear.py`: fault-injected JSON publication failure after durable run completion; verifies fail-soft reads, replay/active-read/selected-read recovery, preservation of other stale markers, and exactly one successful repair write.

Only these four allowed code/test files and this requested report were edited by this job. No commits were made. Parallel keyword changes were not modified.

## TDD evidence

Tests were written before production changes. Targeted command for both RED and GREEN:

```sh
backend/.venv/bin/python -m pytest backend/tests/context/test_session_completion.py backend/tests/context/test_stale_clear.py -q
```

RED output (before fixes):

```text
=========================== short test summary info ============================
FAILED backend/tests/context/test_session_completion.py::test_cluster_result_and_session_milestones[clusters]
FAILED backend/tests/context/test_session_completion.py::test_cluster_result_and_session_milestones[clusters_refined]
FAILED backend/tests/context/test_session_completion.py::test_partial_cluster_files_never_complete[clusters-error]
FAILED backend/tests/context/test_session_completion.py::test_partial_cluster_files_never_complete[clusters-running]
FAILED backend/tests/context/test_session_completion.py::test_partial_cluster_files_never_complete[clusters-not_found]
FAILED backend/tests/context/test_session_completion.py::test_partial_cluster_files_never_complete[clusters_refined-error]
FAILED backend/tests/context/test_session_completion.py::test_partial_cluster_files_never_complete[clusters_refined-running]
FAILED backend/tests/context/test_session_completion.py::test_partial_cluster_files_never_complete[clusters_refined-not_found]
FAILED backend/tests/context/test_session_completion.py::test_restarted_version_does_not_inherit_cluster_job[stage3]
FAILED backend/tests/context/test_session_completion.py::test_restarted_version_does_not_inherit_cluster_job[stage6]
FAILED backend/tests/context/test_stale_clear.py::test_judge_publication_recovers_after_write_failure[replay]
FAILED backend/tests/context/test_stale_clear.py::test_judge_publication_recovers_after_write_failure[active_read]
FAILED backend/tests/context/test_stale_clear.py::test_judge_publication_recovers_after_write_failure[selected_read]
13 failed, 31 passed, 1 warning in 2.86s
```

GREEN output (after fixes):

```text
............................................                             [100%]
=============================== warnings summary ===============================
backend/app/config.py:12
  /Users/persona1/Desktop/dcx_agent-backlog-1/backend/app/config.py:12: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
44 passed, 1 warning in 3.41s
```

## Required full-suite verification

```sh
backend/.venv/bin/python -m pytest backend/tests -q
```

```text
=========================== short test summary info ============================
FAILED backend/tests/keywords/test_autocomplete.py::test_review_progress_after_success_and_failure
FAILED backend/tests/keywords/test_autocomplete.py::test_review_progress_can_stop_superseded_fetch
FAILED backend/tests/keywords/test_rounds_api.py::test_review_r3_loading_gate[False]
FAILED backend/tests/keywords/test_rounds_api.py::test_review_r3_loading_gate[True]
FAILED backend/tests/keywords/test_rounds_api.py::test_review_r3_terminal_snapshot[connected]
FAILED backend/tests/keywords/test_rounds_api.py::test_review_r3_terminal_snapshot[unavailable]
FAILED backend/tests/keywords/test_rounds_api.py::test_review_r3_terminal_snapshot[unconnected]
FAILED backend/tests/keywords/test_rounds_api.py::test_review_r3_terminal_snapshot[stale]
FAILED backend/tests/keywords/test_rounds_api.py::test_review_stale_refresh_recommit_never_reuses_previous
FAILED backend/tests/keywords/test_rounds_api.py::test_review_slow_autocomplete_fetch_keeps_loading
FAILED backend/tests/keywords/test_rounds_api.py::test_review_searchad_fetch_heartbeat
11 failed, 1415 passed, 1 deselected, 2 warnings in 135.98s (0:02:15)
```

The full-suite command exited 1: all 11 failures were the parallel keyword job's new review regressions in `test_autocomplete.py` and `test_rounds_api.py`. Completion/stale tests passed. The full repository suite is therefore not yet green; keyword fixes are outside this job's authorized edit scope.

Tests used local temporary storage and mock/fake services. The suite's autouse guard rejects external network connections, and both targeted modules reject socket connections. No real network requests were used. Scoped `git diff --check` passed. Full raw console captures are available at `/tmp/rfix-completion-red.txt`, `/tmp/rfix-completion-green.txt`, and `/tmp/rfix-completion-full.txt`.

## Scope limitation

Cluster jobs remain session-scoped and in-memory. This fix uses the selected version's existing stage6 stale marker to suppress invalidated inherited results; it does not introduce durable version-scoped cluster publication or infer completion from files after a process restart.
