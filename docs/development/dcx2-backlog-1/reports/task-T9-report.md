# T9 report — AC-06

Status: PASS (measurement); warm overview meets 0.5s target. Default perf exclusion verified; full default suite has failures outside T9.

## Changes

- Added `backend/tests/perf/test_overview_perf.py`, marked `perf`.
- Fixture creates a temporary active v2 session, 310,000 final labels, 31,000 open grade-mismatch queue entries, label events through production triggers, and 310,000 JSONL document metadata records. The real endpoint indexes the documents and populates its caches on the first request. Network connections are blocked; no endpoint or aggregation mocks are used.
- Registered `perf` in `backend/pytest.ini` and set `addopts = -m "not perf"`.
- No change to `backend/app/label/overview.py`: measured warm time was below the threshold.

## Measurement / GREEN

Command: `backend/.venv/bin/python -m pytest backend/tests/perf -m perf -q -s`

| Request | Observed elapsed time |
| --- | --- |
| First (cold application caches) | 14.765615s |
| Second (warm) | 0.284082s |

Result: **1 passed, 1 warning in 22.30s**. No RED was observed; the existing implementation passed on the first measurement. Timers surround each complete TestClient GET, excluding fixture setup and response assertions. Both responses are checked for correct totals, accepted labels, merged labels, distribution, and queue counts; the indexed document count is checked after both calls.

Scope: this synthetic fixture has no completed provider vote-cache rows, human review history, or vector shards. It measures the seeded labels/queue/document workload, including normal reconciliation, automatic audit creation, and estimate caching. It is not a benchmark of all possible session states. The default suite overlapped this measurement, and other jobs were editing the shared checkout.

## Default exclusion / suite check

- `backend/.venv/bin/python -m pytest backend/tests/perf --collect-only -q`: **no tests collected (1 deselected) in 0.27s**, exit 5 as expected for an entirely deselected directory.
- `backend/.venv/bin/python -m pytest backend/tests -q`: **22 failed, 1307 passed, 1 deselected, 2 warnings, 19 errors in 137.22s**. The perf test was excluded.
- Failures were in `test_stale_clear.py` (9), `test_versions_backlog1.py` (5), `test_audit_kind.py` (3), and `test_lease_refresh.py` (5). All 19 setup errors were in `test_autocomplete.py`, reporting a missing `Settings.autocomplete_backend` attribute. These files belong to concurrent work; no fixes were attempted outside T9. This run does not establish a green full suite for the final combined checkout.
- `git diff --check`: passed.

Only the T9 test, pytest configuration, and this report were edited. No commits or package installations.
