# FX-D091: resume done runs with unfinished collections

## Status

Implemented using failing tests first, then the fix, then a small refactor sharing backend eligibility between resume and status. No Git write commands were run. The concurrent script and script-test work was not edited.

## Investigation

**The current worker's normal, intact-data completion path does not produce a detail run that is `done` while `can_finalize` is false.** The API nevertheless accepted such persisted states as unfinished while refusing their resume; the new recovery tests reproduce that discrepancy by seeding the state explicitly.

Evidence (paths relative to repository root):

- `backend/app/crawl/worker.py:418` constructs the detail run with the selected snapshot. `worker.py:420` initializes its outcome to `interrupted`, so an exception does not default to success.
- `backend/app/crawl/worker.py:472` commits the remaining document batch before selecting `done` at line 473; its `finally` invokes `_Run.close` at line 480.
- `backend/app/crawl/worker.py:224`–242 is the final completion guard. Before writing `done`, it checks the selected snapshot for **both pending and leased URLs** (lines 230–233). Remaining work changes the status to `paused` and stop reason to `pending_channels` (lines 234–236). List runs receive the analogous task check at lines 226–228.
- The exception is `target_reached`: `backend/app/crawl/worker.py:137`–140 sets this reason, and line 225 permits completion with outstanding URLs. `worker.py:132`–135 persists both the snapshot and stop reason before `finish_run` at line 242.
- `backend/app/crawl/report.py:78`–90 requires a done detail run and uses the same pending/leased snapshot check, with the same target-reached exception. Pending URLs outside the selected snapshot do not prevent finalization. `_write_report_locked` refuses to create a report when the predicate is false (`report.py:60`–61).
- `backend/app/crawl/queue.py:549`–554 writes the supplied run status without independently validating finalizability. Thus seeded, legacy, externally modified, or damaged persisted state cannot be assumed to satisfy the worker invariant. No ordinary worker path producing the reported mismatch was identified; this is not a claim that arbitrary data corruption or external races are impossible.
- `backend/app/crawl/control.py:469`–490 classifies nonrunning, nonfinalizable collections as unfinished. Previously resume rejected every done run before examining finalizability.

Four regression cases exercise `_Run.close('done')` with pending/leased URLs, with and without target reached: ordinary unfinished runs become paused; target-reached runs remain done and finalizable.

## Changes

- `backend/app/crawl/control.py`: resume now rejects absent runs, completed list runs awaiting gate review, or genuinely finalizable detail collections with the existing `No unfinished phase to resume` error. Done unfinished detail runs use the existing lease reclamation, channel reset, phase launch, and step update. Launch retains `run['kind']` and the manifest snapshot (`control.py:290`–291), so list resumes list and detail resumes detail. `_unfinished_run` at line 251 shares the predicate with status.
- The status payload exposes `resumable`: false for idle, running, completed list runs, and finalizable detail collections; true for nonrunning unfinished list runs and unfinished detail runs (including done detail runs that cannot finalize). The existing router directly returns control status (`backend/app/routers/crawl_v2.py:128`–130), so no router change was necessary. Existing progress does not distinguish outstanding selected-snapshot work sufficiently to duplicate the backend predicate reliably in the UI.
- `frontend/src/lib/api/crawl.ts`: adds optional `resumable` for compatibility with older responses.
- `frontend/src/lib/logic/restartVersion.ts`: blocks version creation for done detail responses marked resumable; adds tested resume visibility logic with the existing interrupted/paused fallback for older responses.
- `frontend/src/app/pipeline/crawling/page.tsx`: uses that visibility helper for the resume controls, preserving the page's existing fresh-setup and disabled-state rules.
- `backend/tests/crawl/test_crawl_api.py`: covers completed-list status and resume rejection while retaining gate-to-detail flow, interrupted/stopped/paused list recovery, done detail recovery (pending/leased), snapshot preservation, status eligibility, exhausted/target-reached rejection, idle/running/absent-run status, worker completion invariants, and damaged-queue classification. Corrected the existing finished-collection fixture to mark its URLs done; previously it only marked the process done and represented precisely the newly recoverable state.
- `frontend/src/lib/logic/restartVersion.test.ts`: covers version blocking, done-run resume visibility, finished rejection, and older-response fallback.

## Missing/corrupt queue behavior and scope

Unchanged: `phase_state` catches `OSError` and `sqlite3.Error` and returns `unfinished` (`backend/app/crawl/control.py:489`–490). Tests cover both an absent queue and corrupt SQLite bytes. This patch does not repair/rebuild queues, add status exception handling, or make those damaged states resumable. Existing resume queue-opening behavior and absent-run rejection remain unchanged. Existing report-file immutability checks also remain in force; inconsistent already-finalized artifacts are outside this repair.

A completed list remains an unfinished collection awaiting detail, so version creation stays blocked. It is not resumable: status returns `resumable=False` and resume returns 409 with `No unfinished phase to resume`. The gate continues to allow detail collection. `report.can_finalize` remains unchanged because collection finalization and list-phase resumability are different conditions.

## Original implementation TDD and verification

Red, before implementation:

- Backend selected recovery/status tests: **7 failed**, `rc=1` (three 409 resume responses; four absent resumable fields).
- Frontend selected restart-version tests: **2 failed, 3 passed**, `rc=1` (resume helper absent).

Green, before final refactor/extra invariant coverage:

- Backend crawl API file: **50 passed**, `rc=0`.
- Frontend restart-version file: **5 passed**, `rc=0`.

Final requested verification:

- `cd backend && .venv/bin/python -m pytest -q --ignore=tests/scripts; echo rc=$?`: **567 passed, 2 warnings; rc=0**.
- `cd frontend && npx vitest run; echo rc=$?`: **24 files, 132 tests passed; rc=0**.
- `npm run lint; echo rc=$?` from frontend: **rc=0**.
- `git diff --check`: **rc=0**.

Frontend emitted a Node module.register deprecation warning. Backend emitted the existing Pydantic class-based config deprecation and joblib physical-core detection fallback warnings. No unrelated warning cleanup was attempted.


## Completed-list gate regression correction

The original shared predicate treated every list run as unfinished because `report.can_finalize` deliberately returns false for all lists. `_unfinished_run` now handles list status separately: a list is resumable only when its run is not done. Detail eligibility still uses `can_finalize`; no-run eligibility remains false. The frontend helper already respects explicit `resumable:false`, so no further frontend production change was needed.

Tests were added before the predicate fix:

- Backend selected list regressions: **2 failed, 3 passed; rc=1**. Completed-list status incorrectly returned true and resume incorrectly returned 200.
- Frontend restart-version tests: **6 passed; rc=0**. The new completed-list assertion passed immediately, including with stale paused-channel information; no frontend failure is claimed.
- After the fix, the crawl API file passed **59 tests; rc=0**, including the existing gate-flow tests. An additional absent-run regression was then added for full-suite verification.

Final correction verification:

- `cd backend && .venv/bin/python -m pytest -q --ignore=tests/scripts; echo rc=$?`: **572 passed, 2 warnings; rc=0**.
- Frontend full Vitest suite: **24 files, 133 tests passed; rc=0**.
- `cd frontend && npm run lint; echo rc=$?`: **rc=0**.
- `git diff --check`: **rc=0**.

No Git write commands were run. Existing uncommitted work was preserved; `scripts/capture_http_fixture.py` and `backend/tests/scripts/` were not edited.
