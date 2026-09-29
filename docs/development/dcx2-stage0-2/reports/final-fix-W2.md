# FINAL fix W2 — backend crawl pipeline

## Fixes and coverage

- C1 / R-57: fixture dates are today minus 364 days plus row modulo 365. An adapter captures today once; constructor and row-date helper accept a frozen date. T12 `test_fetch_returns_body`, `test_fixture_dates_wrap_every_year`, and integration `test_default_crawl_config_reaches_preprocess` cover frozen dates, wrapping, and 200 documents reaching preprocessing using default date filters.
- I1: list/detail runs finish as `paused` when pending/leased work remains, unless detail reached its document target. Worker state records `stopReason=pending_channels`, channel statuses and `paused_channels`. Report creation verifies detail completion and snapshot exhaustion. `test_pause_resume[list/detail]`, `test_done_with_pending_does_not_freeze_report`, and `test_resume_without_body_clears_pause` cover resumability and report immutability boundaries.
- Codex #6: list filtering runs before persistence. Queue `record_list_page(..., filter_rules=...)` inserts discoveries, filter status/rule, page completion and next cursor in one transaction. `test_filter_crash_before_commit` and `test_record_page_rolls_back_filter_with_page` inject crashes before persistence and after insertion.
- I4: `errors.safe_error` intentionally emits codes only, never exception messages. Worker retries, exhausted-row errors, fatal stderr and report error summaries use it. Control does not persist/log caught exception text. `test_safe_errors` checks filesystem paths, query strings and a configured sentinel secret across last_error, status, report and CLI stderr (the stream redirected into worker logs). Existing CLI/fallback expectations now assert codes.
- I5: liveness requires a live PID plus a fresh heartbeat (STALE_AFTER_S; 30 seconds for starting reservations). Stale live processes receive SIGTERM only when inspected command arguments contain app.crawl.worker; unavailable inspection skips killing. `test_stale_alive_worker` and `test_stale_pid_killed_only_if_worker` cover stale/reused PID behavior and relaunch.
- Codex #10: report matrix full/snippet/restricted sums doc_count for every keyword hit. URL discovery/completion counts remain explicit. `test_document_counts` covers 200- and zero-document URLs; `test_shared_multidoc_count` covers shared keyword hits and restricted/snippet documents. T14 matrix contract test updated.
- R-59: public read-only `phase_state(sid)` returns none/running/unfinished/done. A completed list remains unfinished until detail completes; it never creates a queue, reclaims leases, kills a PID or writes a report. Pause/liveness tests cover the guard. New collection creation confirms stage2 using the store's `_update_locked(..., confirm_stage="stage2")`, the lock-held implementation of update_session. Calling public update_session while holding the existing non-reentrant flock would deadlock. A narrow unsupported-keyword fallback supports the pre-W1 store. `test_start_list_confirms_only_stage2` verifies stage1 stale state is retained.
- R-63: gate thresholds come from settings; gate rows declare `count_unit="urls"`. Default channels are project-context channels intersected with available sources. New collections reset crawlExcluded and gate exclusions; normalized keys drive ancestry, deduplication and gate comparisons. `test_gate_settings`, `test_context_channels_norm_and_fresh_flags`, `test_context_channel_intersection`, and `test_gate_normalized_exclusion` cover these rules.

## W3 status/resume/report contract

- A paused run is stored as `runs.status="paused"`; GET status exposes `status="interrupted"`, `channels[source].status="paused_blocked"|"paused_parse_error"`, `paused_channels: string[]` and `stopReason`. Progress and collection identity remain available; report stays null.
- POST resume accepts no body or `{"min_interval_s":{"fixture":1.5}}`. Values must be finite and nonnegative; unknown channels return 422. The supplied values update the collection manifest's perChannel and channel_limits for the new worker. Specified channels clear their pause/counters; other paused channels stay paused. No-body resume retries all paused channels with existing intervals. Editing a running worker's intervals is rejected.
- report.json is written only for a completed detail run with no pending/leased snapshot URLs, or target_reached. A paused collection remains writable/resumable.
- Report matrix cells retain listed/filtered/excluded/unique as URL counts for compatibility. full/snippet/restricted are document counts. New urls_listed and urls_done are explicit URL counters, also present in totals. counts[kw][source] is full + snippet documents, including shared keyword hits. Gate counts remain URL-based and declare count_unit.

## TDD results

Initial regression command:
`cd backend && .venv/bin/python -m pytest tests/crawl/test_final_w2.py tests/crawl/test_fixture_adapter.py tests/test_integration_stage0_2.py::test_default_crawl_config_reaches_preprocess -q`

```text
10 failed, 9 passed, 1 warning in 1.98s
```

Failures covered all original regressions: stale liveness, both paused phases, filter crash, document counts, leaked errors, normalized fresh keywords, gate settings, frozen fixture date, and default-window preprocessing.

Additional normalized gate exclusion regression:
```text
1 failed, 13 passed, 1 warning in 1.36s
```

The new default-window e2e owns its synthetic corpus so it does not depend on concurrent shared corpus edits. Four existing e2e scenarios currently find zero URLs: the shared make_corpus.py now emits curated fixture keywords while their offline LLM fixture still emits 냉방{round}단어{index}. Per task instructions, that concurrent mismatch is not repaired here.

Final command outputs and commit outcome follow.

The concurrent corpus mismatch was resolved externally during validation. No W1-owned file was edited by W2.

Final GREEN:
```text
cd backend && .venv/bin/python -m pytest tests/crawl tests/test_integration_stage0_2.py -q
235 passed, 2 warnings in 25.61s

cd backend && .venv/bin/python -m pytest -q
522 passed, 2 warnings in 33.61s
```

Warnings are the existing Pydantic class Config deprecation and joblib physical-core detection fallback. `git diff --check` passes. No external adapters/network were used.

Earlier full-suite attempt: 4 failed, 507 passed, 1 warning in 30.30s, all four failures from the concurrent corpus mismatch described above. This is superseded by final GREEN.

## Commit outcome

**uncommitted**. Scoped staging failed with exit 128:
```text
fatal: Unable to create '/Users/persona1/Desktop/dcx_agent/.git/worktrees/dcx_agent-dcx2-stage0-2/index.lock': Operation not permitted
```

The requested scoped commit was also attempted, with subject:
`fix: 최종 리뷰 W2 — fixture 날짜, 일시정지 재개, P1 필터 원자성, 오류 정제, 생존 판정, 문서 수 집계`
and trailer:
`Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

It failed with exit 1 because the three new files could not be staged and were unknown to Git. No permission bypass or unrelated-file commit was attempted.

## Follow-up FX-B

- N1: `phase_state(sid, collection_id=None)` accepts an explicit collection. Forking checks the source version's collection, including older read-only sources; a source without a collection stays detached. Regression tests cover repeated forks from a stopped c1 after v2 detached, and retaining completed c1 while active v2 has an unfinished c2.
- N2: stale runs are marked interrupted before SIGTERM and state reset. Worker `save()` checks that its run is both latest and running inside a SQLite write transaction, held through atomic state replacement. This serializes saves against fencing and new run registration. Normal close saves terminal channel state before finishing the run. Confirmed worker PIDs receive SIGTERM followed by polling for exit for at most five seconds; after timeout the fence still prevents old saves. Tests cover fenced saves/close before and after replacement, a newer starting reservation, exit polling, and the five-second bound.
- N3: deleting a versioned session skips `assert_writable` only when loading returns no session or fails with a read/decode error. Root path validation and writable checks for readable sessions remain. Missing/corrupt JSON deletion and invalid session paths are tested.
- N4: removed both transitional fallbacks; version phase checks directly use the public helper, and crawl mutations directly use `_update_locked(..., confirm_stage=...)`.
- M1 support: crawl errors retain their existing HTTP status, `kind`, and `message`, and add `error.code`. Equivalent worker-running errors share one code. Validation and storage envelopes also have codes.

Error code list:

| Code | Meaning |
| --- | --- |
| `sources_unavailable` | Requested sources are unavailable |
| `worker_running` | A worker or another crawl phase is running |
| `invalid_request` | Request validation failed |
| `unknown_resume_channel` | Resume intervals name an unknown channel |
| `p1_unfinished` | List collection must finish before detail |
| `finished_collection` | Completed collection is immutable |
| `readonly_version` | Selected version is read-only |
| `version_conflict` | Displayed version differs from active version |
| `session_not_found` | Session does not exist |
| `invalid_session_id` | Invalid session identifier |
| `invalid_version` | Invalid version identifier |
| `no_collection` | No valid crawl collection is selected |
| `invalid_list_mode` | Unsupported list mode |
| `parent_collection_required` | Added-keywords mode needs a parent |
| `invalid_collection_ancestry` | Invalid or cyclic collection ancestry |
| `parent_collection_not_found` | Parent collection metadata is missing |
| `no_approved_keywords` | No approved new keywords to collect |
| `collection_conflict` | Active collection changed before launch |
| `snapshot_not_found` | Requested snapshot does not exist |
| `snapshot_conflict` | Another detail snapshot is already selected |
| `detail_unfinished` | Existing detail phase must be resumed |
| `no_unfinished_phase` | No unfinished phase is available to resume |
| `gate_not_editable` | Gate cannot be edited in the current phase |
| `unknown_gate_keyword` | Gate exclusion names an unknown keyword |
| `legacy_session` | Legacy session cannot edit stages 0–2 |
| `storage_error` | Storage or worker OS operation failed |
| `crawl_error` | Fallback for an otherwise unmapped StoreError |

TDD: `tests/crawl/test_followup_fx_b.py` initially reported **15 failed** before production edits. Focused context/crawl regression validation then passed **87 tests**. The first full-suite GREEN was **537 passed, 2 warnings in 36.40s**. Four additional boundary checks were added before final full-suite verification below. Existing phase-helper mocks were updated for the optional collection argument.

Final GREEN: `cd backend && .venv/bin/python -m pytest -q` — **541 passed, 2 warnings in 36.80s**. All 19 follow-up tests pass. Scoped `git diff --check` passes. Warnings remain the existing Pydantic class-config deprecation and joblib physical-core fallback. Frontend and unrelated `.DS_Store` edits are excluded.

Commit outcome: **uncommitted**. Explicit scoped `git add` failed (exit 128): the sandbox denied creation of `/Users/persona1/Desktop/dcx_agent/.git/worktrees/dcx_agent-dcx2-stage0-2/index.lock`. The requested subject and `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` trailer were then passed to a scoped `git commit --only`; it failed (exit 1) because the new regression test could not be staged. Changes are left uncommitted as requested.

## Follow-up FX-B2

- R-66: `GET /crawl/{sid}/status` now adds `collection_channels` from the active collection manifest and `min_interval_s` for each manifest channel. Without a collection these are `[]` and `{}`. All existing status fields remain unchanged.
- Intervals follow worker `_Run` precedence: manifest `config.perChannel`, falling back to `config.channel_limits`, then 1 second for clien/ppomppu or 0 for other channels. Resume interval updates are reflected on the next status read; session config edits do not override the active manifest.
- TDD: five new parameterized cases initially failed for missing fields. Coverage includes no collection, defaults, both manifest config forms and their precedence, and a raised interval after API resume.
- Verification: `cd backend && .venv/bin/python -m pytest tests/crawl -q` — **223 passed, 1 warning in 25.41s**. The warning is the existing Pydantic class-config deprecation. Scoped `git diff --check` passes.
- Commit outcome: **uncommitted**. Scoped `git add` and `git commit --only` with the requested subject and co-author trailer both failed (exit 128): the sandbox denied creation of `/Users/persona1/Desktop/dcx_agent/.git/worktrees/dcx_agent-dcx2-stage0-2/index.lock`. Changes remain uncommitted; no frontend files were touched.
