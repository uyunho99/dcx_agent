# QA2 Q5 fix — round 1 report

## Status
Completed all three required fixes using RED → GREEN. Changes are uncommitted; no commit was attempted. No subagents or backend changes.

## Files
- `frontend/src/app/pipeline/training/page.tsx`: swallow post-export session refresh rejection so the successful export still proceeds through patchSession and redirect.
- `frontend/src/components/prep/PrepScreen.tsx`: swallow refresh rejection after immediate completion and polling completion, preserving the completed result without action-error recovery or extra polling.
- `frontend/src/app/pipeline/clustering/page.tsx`: restore read/poll eligibility for historical versions; existing write and refresh guards remain.
- Corresponding `page.test.ts` files and `PrepScreen.test.ts`: five new regression cases, using the existing component hook harness.

## RED
Before implementation changes, ran:

`npm --prefix frontend test -- --run src/app/pipeline/training/page.test.ts src/components/prep/PrepScreen.test.ts src/app/pipeline/clustering/page.test.ts`

Result: 5 failed, 10 passed. Expected failures:
- Both model and model-free exports skipped patchSession when refresh rejected (zero calls).
- Immediate prep completion performed an extra status recovery read (2 instead of 1).
- Polled prep completion scheduled another status read after refresh rejection (4 instead of 3).
- Historical clustering reads were disabled (`enabled` was false).

## GREEN
- Same targeted command: 15 passed across 3 files.
- `npm --prefix frontend test -- --run`: 318 passed across 49 files.
- `npm --prefix frontend run lint`: passed, exit 0, no findings.

Regressions also verify training redirect, no action error banner or automatic re-export, retained prep completion, historical cluster content rendering, and blocked historical writes/refresh.

## Concerns
- Optional shared refresh sequence guard and additional export-hook deduplication were not introduced. The tested successful export paths invoke refresh once; broader overlapping-refresh behavior remains unchanged.
- Tests use the repository's existing mocked-hook harness; no live browser QA was run in this implementation round.
- Vitest emitted a non-failing Node `module.register()` deprecation warning.
