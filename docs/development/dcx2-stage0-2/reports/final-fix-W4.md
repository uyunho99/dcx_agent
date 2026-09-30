# Final fix W4

Date: 2026-09-29. Scope: real-channel final review, D-094 / D-095. Offline execution; no git writes, no live-site requests. `03-plan.md`, `scripts/capture_http_fixture.py`, and `backend/tests/scripts` were not edited.

## Changes

- Channel settings use `status.available_sources` for both enabled controls and the internal `사용 가능` / `사용 불가` badge. Naver copy is `검색 결과 화면 · 본문`; cafe additionally states `회원 전용 글은 요약`.
- Removed `naver_search` and YouTube key entries from integration dependencies. Shopping remains visible as permanently terminated, with `connected=false`, no credential names, and a fixed termination explanation even when keys are configured. The drawer shows `서비스 종료` without an entry retry action. Counts derive from the returned four entries. The endpoint still returns public metadata only, never secret values.
- Cafe search rows retain the display name in `src_meta.cafe`, alongside `cafe_id`. Existing source filtering matches either name or slug. Detail JSON overrides the name from `result.cafe.name` (also accepts `cafeName`) or restricted-response `result.more.cafeName` while preserving the slug.
- Synthetic cafe rows cover absolute dates, relative dates, and missing dates. Restricted documents retain the list date. Existing date parsing already handled these row elements; no parser rewrite was needed. Unknown dates remain included by date filters, as documented beside the filter and tested here.
- Worker forwards `youtube.videos_per_keyword` to the adapter's actual `ytsearchN` request (20 when omitted). Existing queue caps and compatibility with injected legacy adapters remain. Timestamp dates use `Asia/Seoul`, including the UTC-to-KST midnight boundary; date-only upload dates remain unchanged.
- Naver backend worker defaults, status-reported intervals, and frontend defaults are concurrency 1 / interval 1 second. Increasing the resume interval doubles this to 2 seconds. Explicit saved configurations retain their overrides.
- `KeyError`, `AttributeError`, and `IndexError` now contribute to the parse-error pause threshold, alongside `ValueError` and `TypeError`.
- Built-in real adapters expose settings-sensitive class-level availability. Status polls no longer construct their HTTP clients. Custom injected factory lifecycle behavior remains supported.

## Offline QA flag

`REAL_CHANNELS_ENABLED` is a boolean backend setting, default `true`. For an offline QA backend/worker process set:

```sh
REAL_CHANNELS_ENABLED=false
ENABLE_FIXTURE_CHANNEL=true
FIXTURE_CORPUS_PATH=/absolute/path/to/local-corpus.csv
```

Restart existing processes after changing their environment. All five real adapters then report unavailable, while fixture availability is unchanged. With fixture enabled and a corpus path configured, `available_sources()` returns exactly `['fixture']`. Tests also toggle the settings in-process to ensure there is no stale availability cache. This flag controls channel availability; it is not a network sandbox for unrelated integrations or direct adapter calls. The existing crawl test socket guard and mocked HTTP/yt-dlp responses keep regression tests offline.

## TDD and verification

Before implementation the new W4 backend suite reported 14 failures and the frontend suite reported 3 failures. Two test setup mistakes were corrected (recorded public cafe JSON uses `name`; queue setup requires `KwMeta`). The corrected YouTube test was separately run against the old worker call and failed on the 10-versus-23 search limit, then passed after restoring the fix. A separate status-interval regression failed on 0-versus-1 seconds before the status fallback was fixed. Date-only assertions already passed against existing parsing; the combined cafe-row contracts failed on the missing display name.

The first full backend run returned rc=1 (785 passed, 2 failed): an obsolete six-entry integration assertion and a concurrency test relying on the old Naver default. Updated the integration contract and gave the concurrency test explicit limiters, preserving its cross-channel and within-channel parallelism assertions. Final full backend rerun: `cd backend && .venv/bin/python -m pytest -q; echo rc=$?` returned rc=0: 788 passed in 77.83 seconds. Two existing warnings remain: Pydantic class-based configuration deprecation and joblib physical-core detection falling back to logical cores.

Frontend final: `npx vitest run` rc=0, 25 files / 137 tests passed. `npm run lint` rc=0. `git diff --check` rc=0.

## Files changed

- `backend/app/config.py`
- `backend/app/crawl/adapters/{__init__,community,naver_common,naver_cafe,youtube}.py`
- `backend/app/crawl/{control,filters,worker}.py`
- `backend/app/external/base.py`
- `backend/tests/context/test_api.py`
- `backend/tests/crawl/{test_final_w4,test_resume}.py`
- `frontend/src/app/pipeline/layout.tsx`
- `frontend/src/components/crawl/Settings.tsx`
- `frontend/src/components/internal/IntegrationsDrawer.tsx`
- `frontend/src/lib/logic/{crawlConfig.ts,finalW4.test.ts,__fixtures__/integrations.json}`
- This report.

## Concerns

Live browser/site behavior was not rechecked because this task prohibits network access. Frontend status/copy coverage uses source contracts and logic tests. Availability indicates configured local capability, not guaranteed site reachability. Existing `.DS_Store` changes were left untouched. The legacy shopping request wrapper is outside this integration-metadata fix; the reported integration is permanently unavailable.
