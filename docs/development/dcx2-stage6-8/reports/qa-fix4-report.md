# QA-S7b fix report

Status: fixed on `feature/dcx2-stage6-8`.

## Changes

- Added `MetricsComparison` for stage3/stage4/stage5 responses, including the `same` banner, version column headings, and metric rows from the union of each entry's before/after keys. Values use `printable`; null/missing values show `—`, and entries with neither saved side show `저장된 결과가 없습니다.`.
- Preserved stage0/1/2/6 routing. Remaining results use `FileComparison` only when both top-level before/after values are non-null objects; otherwise they use `MetricsComparison`.
- Made file key enumeration and value access null-safe with `before ?? {}` and `after ?? {}`.
- Added coverage for multiple metric entries, keys present on only one side, stage4/stage5's `stage_5` response, empty entries, stage7 file routing, and direct FileComparison rendering with either side null. The test harness captures the routed renderer without adding a page export.

## TDD verification

1. **RED** — `npm --prefix frontend test -- compare` exited 1: 7 failed, 5 passed across 2 files. All seven regression failures reproduced `TypeError: Cannot convert undefined or null to object` in `FileComparison`. Existing stage6 and stage7 file rendering passed. An initial run had the same counts but Suspense hid the metrics exceptions behind its fallback; rendering the screen inside that boundary exposed the actual exception before implementation changed.
2. **GREEN** — `npm --prefix frontend test -- compare` exited 0: 12 tests passed across 2 files after the implementation fix.
3. **Refactor** — Expanded FileComparison formatting around the normalized before/after values and reused the comparison-rendering test helper for stage6. Re-ran `npm --prefix frontend test -- compare`: exit 0, 12 tests passed across 2 files.
4. **Full suite** — `npm --prefix frontend test` exited 0: 467 tests passed across 52 files.
5. **Lint** — `npm --prefix frontend run lint` exited 0 with no diagnostics.

`git diff --check` also passed. Next build was skipped as requested.

## Concerns and scope

No outstanding functional concerns found. Vitest emitted Node's `DEP0205` warning about `module.register()` during both RED and passing runs; it did not affect results. No browser smoke test or build was run.

Only the two requested compare files and this report were edited by this task. Other worktree changes were left untouched. No staging or commit was performed.
