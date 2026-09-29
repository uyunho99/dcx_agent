# W5 — D-096 / D-097

Status: complete. D-096/D-097 implemented; all requested verification commands pass.

## Behavior

- D-091 remains enforced for running, stopped, interrupted, and paused collections. D-096 adds `gate` for a completed latest LIST run: version creation succeeds, sets only the new version's `collectionId` to null, and leaves the source session snapshot untouched.
- `POST /crawl/{sid}/finish-partial?version=...` follows the existing writable-version guard and crawl error envelope. It rejects live workers, non-detail phases, absent eligible pauses, and unfinished work in other channels with 409.
- D-097 explicitly includes both `paused_blocked` and `paused_parse_error`. Remaining pending/leased URLs in the selected detail snapshot become `skipped`, with reason `blocked` or `parse_error`; leases are cleared and the run becomes done in the same SQLite transaction. Completed documents remain available for preprocessing and collection inheritance by subsequent versions.
- Existing queue databases gain the `skipped` CHECK value by an atomic table rebuild preserving URL columns/data and logical snapshot membership. Reopening is idempotent.
- Status exposes `remaining_by_channel`. Report channels expose `skipped` and `skip_reason`. Skipped URLs are removed from the progress target while remaining visible in report totals.
- The stopped banner offers “여기까지로 마치기” for eligible detail pauses, asks for confirmation with each channel's remaining count/reason, and displays those counts in P5, e.g. “뽐뿌 300건 미수집(차단)”.

## TDD and verification

- Before implementation: new backend tests failed (8 failures, rc=1); frontend gate expectations failed and the new partial-finish module was absent (rc=1).
- Targeted backend contracts after implementation: 71 passed, rc=0.
- A progress-target regression was added and observed failing (rc=1) before subtracting skipped URLs.
- Initial full pytest: 799 passed, 2 failed, rc=1. Both failures were existing completed-LIST expectations superseded by D-096; updated to `gate`.
- `cd backend && .venv/bin/python -m pytest -q`: 803 passed, 2 existing warnings; rc=0 (77.12s).
- `cd frontend && npx vitest run`: 26 files, 139 tests passed; rc=0.
- `cd frontend && npm run lint`: rc=0.
- Additional `npx --no-install tsc --noEmit --incremental false`: rc=2. Existing unrelated `src/lib/logic/crawlLoad.test.ts:30` assigns a session whose `drafts` type has no fields in common with `CrawlSession.drafts`. This task did not change that test or the `CrawlSession` type.
- Whitespace diff check for owned changes: rc=0.

## Files changed by W5

- `backend/app/context/versions.py`
- `backend/app/crawl/control.py`
- `backend/app/crawl/queue.py`
- `backend/app/crawl/report.py`
- `backend/app/routers/crawl_v2.py`
- `backend/tests/context/test_w1_crawl_contract.py`
- `backend/tests/crawl/test_crawl_api.py`
- `backend/tests/crawl/test_final_w5.py` (new)
- `frontend/src/app/pipeline/crawling/page.tsx`
- `frontend/src/components/crawl/Progress.tsx`
- `frontend/src/lib/api/crawl.ts`
- `frontend/src/lib/api/errors.ts`
- `frontend/src/lib/logic/restartVersion.ts`
- `frontend/src/lib/logic/restartVersion.test.ts`
- `frontend/src/lib/logic/finishPartial.ts` (new)
- `frontend/src/lib/logic/finishPartial.test.ts` (new)
- `docs/development/dcx2-stage0-2/reports/final-fix-W5.md` (this report)

## Concerns and scope

- Browser interaction was not manually exercised; button eligibility and confirmation content are covered by Vitest pure-function tests, consistent with D-071.
- Existing typecheck failure above remains outside this narrow task.
- No git writes or network commands were performed. Did not edit `scripts/capture_http_fixture.py`, `backend/tests/scripts`, or `backend/tests/fixtures/**`. Concurrent/pre-existing changes elsewhere were left untouched.
