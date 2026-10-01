### Spec Compliance
- ✅ **T1 adapter** (`backend/app/external/naver_autocomplete.py:60-91`): request params, User-Agent, 10s timeout and 1s gap between seeds match. Dedupe keeps the best rank per `norm_key` (`:82-85`), in first-seen order. A partial failure counts `failed`, and zero results raise `AutocompleteUnavailable`. Fake mode never builds a client.
- ✅ **T2 metrics** (`backend/app/keywords/coverage.py:57-120`): weights are 1/rank. There are three bands labelled `1~3위`/`4~6위`/`7~10위`, and an empty band gives `None`. Rank mode sets `m2=None`, `m7=None` and `m7_reason='no_volume'`, and `missing_top` is sorted by rank ascending, capped at 20. In volume mode the sort, deciles, m1 and m7 are unchanged (AC-13 calculation kept).
- ✅ **Contract**: `status`, `source`, `weighting`, `seeds`/`failedSeeds` (camelCase), the `m2_bands` labels and `m7_reason` agree between backend and `frontend/src/lib/types.ts`. The second value in `missing_top` is shown as `자동완성 순위` for autocomplete and `월간 검색수` for searchad.
- ✅ **Seeds** (`rounds.py:387-389`): `[bk]` plus the first 20 approved `origin=='llm'` keywords, using a stable sort by round.
- ✅ **Background run and lock**: `begin` saves `loading` with `startedAt` under `mutate`. `finish` checks `status=='loading'` and that `startedAt` still matches, so a run that was superseded never overwrites a newer result. The stale check is `coverage_status` (`rounds.py:340-350`, >120s), applied in GET (`keywords_v2.py`) and in R3 `_inputs`. `refresh` deduplicates while a run is loading.
- ✅ **Copy text (T4)**: the loading, unavailable, `② 순위 구간별 커버리지`, `—`, `계산 불가(검색량 없음)`, `자동완성 순위`, `자동완성 검색어를 모두 덮고 있습니다.`, `질의 N개 중 M개 실패`, `실패한 질의 N개` and R3 wait strings all match. The R-114 text and the searchad evidence row are unchanged.
- ✅ **Polling** (`CoveragePanel.tsx` `startCoveragePolling`): runs every 3s, stops on any status other than loading, and cleanup cancels it. The R3 start, regenerate and "다음 라운드" buttons are disabled while loading (`page.tsx:51,160`). The refresh button uses `loading` (disabled), and the loading text has `aria-live`.
- ✅ **T12**: the autouse fake backend plus the `pytest.fail` (BaseException) connect guard get past `except Exception`.
- ⚠️ **AC-10 / AC-13 caching semantics**: see Important 1.

### Issues
**Critical**: none.

**Important**
1. **Re-committing R2 never recalculates coverage** (`rounds.py:332` calls `compute_coverage` without refresh, and `:359` returns the saved value). Before this change, every call recalculated m1/m2/missing_top/llm_only from the cached `humanQueries` and the current approved set. Now any saved coverage is returned as-is.
   - Scenario: commit R2 with approved set A, then regenerate R2 (replacing), approve set B and commit again. Coverage, the `llm_only` badges and the `missing_top` that feeds R3 (AC-12) all still reflect set A. This affects the searchad path too, which is a behaviour change against AC-13. The pre-existing test was rewritten to accept it (`test_unconnected_coverage_replaces_old_failure` became `test_coverage_preserves_old_failure_until_refresh`).
   - Also, "다시 계산하기" now refetches searchad as well, where it used to reuse the stored queries.
   - Suggested fix: without refresh, recalculate from the saved `humanQueries` (no fetch). Only `refresh=true` should refetch.
2. **The 2-minute stale window includes LLM axis classification** (`rounds.py:395-401`). `kw_axis_classify` now runs inside the background job, before `finish`.
   - Scenario: with the codex backend (`codex_timeout_s=600`), about 21s of autocomplete plus 60-120s of classification goes over 120s. GET reports `unavailable`/`interrupted`, polling stops, the card says autocomplete could not be fetched, and R3 unlocks with coverage text '계산 실패'. Later the job writes `connected` (its `startedAt` still matches), but the UI never picks it up.
   - Suggested fix: a larger threshold or a heartbeat, or classify after saving the human queries.

**Minor**
- The `bk` seed is not filtered (`rounds.py:389`), unlike the searchad hints. An empty `bk` sends `q=''`, which causes a spurious "질의 21개 중 1개 실패" on the card.
- The loading interpretation always says "네이버 자동완성…(약 20초)", even while a searchad fetch is running. On a first load, `m1==null` also makes the headline read "커버리지 계산 불가".
- A stale `interrupted` state keeps the previous m1/missing_top (`{**saved}`). The metrics card shows old percentages under the "계산 불가" headline, and the evidence row shows `실패한 질의 0개`.
- R3 receives rank numbers as bare JSON `[q, rank]`, with no label saying they are ranks, not volumes.
- The "커버리지를 받는 중입니다…" line shows in any round while loading (for example R4 after a refresh), and there is no page-level test for the R3 block.
- The network guard does not block DNS (`getaddrinfo`), and a connect attempt inside a real background thread would not fail the test.

### Assessment
The contract, copy text, polling, rank metrics and network isolation are solid. The caching change (Important 1) leaves coverage stale after an R2 re-commit, on both sources, and the stale-loading threshold misreads slow LLM classification as a failure.

Task quality: Needs fixes
