# Branch review 1

Reviewed `feature/dcx2-backlog-1` at `675760a`, against `40ca7fe`, using `01-brainstorm.md` (AC-01–14), `02-design.md`, and `03-plan.md`. The parked minors at the end of `.superpowers/sdd/03-plan/progress.md` are excluded.

## 1. Important — Live autocomplete collection expires before its heartbeat starts

**Location:** `backend/app/keywords/rounds.py:422`, `backend/app/keywords/rounds.py:349` (heartbeat starts at line 438).

`suggestions()` completes every sequential HTTP request before the first progress update. The 30-second heartbeat protects only classification. With 21 seeds, even successful responses within the individual 10-second timeout can exceed the 120-second stale threshold. Reads then report `unavailable/interrupted` although the worker is alive.

**Concrete reproduction:** Use a product name plus 20 approved LLM keywords, no SearchAd credentials, and an HTTP transport returning valid suggestions after nine seconds per request. Commit R2 and poll coverage. Collection takes `21 × 9 + 20 × 1 = 209` seconds. After 120 seconds, GET projects `unavailable`; collection subsequently succeeds and persists `connected`.

**Observed validation:** An in-memory clock and `httpx.MockTransport` reproduced `unavailable` at simulated second 129 while collection was still executing, followed by `connected` at second 209. All 21 requests succeeded; no real HTTP was used.

**Impact:** `startCoveragePolling()` stops on that first terminal response (`frontend/src/components/keywords/CoveragePanel.tsx:53`). The page does not automatically display the eventual result and enables R3 prematurely. Clicking refresh can also launch another collection while the original fetch is still running. This undermines AC-09/10/12 and the loading contract.

**Suggested correction:** Maintain an ownership-checked heartbeat throughout fetching and classification, or update progress after each seed with an appropriate bounded-request watchdog.

## 2. Important — R3 can start during coverage collection and permanently omit its signals

**Location:** `backend/app/keywords/rounds.py:186` (loading coverage becomes empty input), `backend/app/keywords/rounds.py:116` (round admission checks only preceding commits).

The new asynchronous coverage workflow relies entirely on the requesting browser's `coverageLoading` flag to prevent R3 generation. The backend accepts R3 while coverage is loading, and `_inputs()` silently assigns an empty `coverage_signals` string. Completing coverage later does not update the already-generated round.

**Concrete reproduction:** Open the same session in two tabs after R2 and coverage have completed, before generating R3. In tab B, click “다시 계산하기” and hold the autocomplete response. Tab A retains its previously connected coverage and has no coverage poll running. Click “다음 라운드 생성” in tab A. Its `POST /keywords/{sid}/rounds/3?version=v1` is accepted while the server's coverage is loading. R3 receives no missing-query signals. Equivalently, issue that POST immediately after R2 commit while background coverage is pending.

**Observed validation:** Calling the real `start_round()` and `_inputs()` with in-memory storage, committed R1/R2, and fresh loading coverage produced `job.status='running'`, scheduled one execution, and returned `coverage_signals=''`.

**Impact:** A normal multi-tab interaction loses the AC-12 coverage input without a failure or warning. Unlike finding 1, this requires neither slow HTTP nor an expired job.

**Suggested correction:** Enforce the loading gate under the same session lock that admits R3. Also ensure a refresh cannot change the input between admission and the worker's input capture; preserve or atomically capture the intended coverage snapshot. Terminal unavailable coverage should still allow progression under AC-11.

## 3. Minor — Cluster completion accepts stale or partially written results

**Location:** `backend/app/routers/sessions.py:46`.

`clusters_done()` treats any session-scoped completed cluster job, or any nonempty cluster file, as completion for every selected version. It neither checks the version's stale markers nor respects an explicitly running/failed cluster job before falling back to files. `completedThrough()` then returns 6 and marks all preceding stages complete, even when their explicit server completion values are false.

**Concrete reproduction:** Complete clustering in v1, then create v2 restarting from stage3. Read `/session/{sid}?version=v2`. The retained session-scoped v1 cluster job/files yield `clustersDone=true` despite stale preprocessing, labeling, training, and clustering. A fresh page load therefore checks the stages through clustering. A second reproduction is to let clustering write its first output file and then fail writing a later file: `backend/app/services/clustering.py:102` writes files individually before publishing done, but the failed run is nevertheless projected as completed.

**Observed validation:** In-memory probes returned `clustersDone=true` both for a v2 session with stale stage3/stage6 and an old completed cluster job, and for `job.status='error'` with one nonempty partial output file. Other completion fields remained false.

**Impact:** AC-08 shows unfinished work as complete, including on reload. This is independent of the parked issue concerning stale client-side completion values.

**Suggested correction:** Tie cluster completion to a successful result generation and its input/version provenance. Do not infer success from partial files or override known running/error state with file existence; suppress inherited results invalidated by the selected version's restart.

## 4. Minor — Stage-4 completion cannot recover a failed session publication

**Location:** `backend/app/context/stale.py:47`, with the terminal transition at line 35 and early return at line 39.

`judge_done()` commits the run's terminal `done` state before writing `labeling.status` and removing `stale.stage4` from session JSON. A process crash or write failure between these commits leaves both judge runs done and the stale marker intact. Replaying `judge_done()` for the same run returns immediately because its UPDATE matches only running rows. The generic worker's final UPDATE also excludes done rows, so even a publication exception cannot make the run retryable.

**Concrete reproduction:** Start with Jev done, GPT running, and `stale.stage4` present. Inject an `OSError` on the session `write_json()` inside `judge_done()` (or terminate the process after its SQLite commit). Restore writes and restart/read the session. The runs are both done, but the stale banner persists; replaying completion for that run does not repair it.

**Observed validation:** Used SQLite `:memory:` with the real completion function and a fault-injected JSON writer. After the exception, both rows were `done` while saved labeling remained stale. A second invocation attempted zero JSON writes.

**Impact:** AC-07 remains false after a successful judgment run and restart, while the completion projection can report labeling done. This is distinct from the parked same-version rejudge status-reset issue.

**Suggested correction:** Make session publication recoverable and idempotent for already-done runs, or reconcile completed run evidence with pending stale-marker removal on recovery.

## Validation and boundaries

- Reviewed production changes and adjacent callers for coverage, worker leases, version activation/cleanup, audit scheduling/migration, stage publication, and frontend completion contracts.
- The audit column migration is serialized by `LabelStore._db()` using `BEGIN IMMEDIATE`; no additional confirmed SQLite migration defect was found.
- Inspected autocomplete response validation and the new test network guard. No real external requests were made during this review.
- Reproductions used Python `-B`, mocked storage/HTTP, simulated time, and SQLite `:memory:`. The repository test suites were not rerun because they create files; this preserves the requested report-only write boundary.
- Only this report was written. No implementation or test files were changed.

Status: Critical 0 | Important 2 | Minor 2
