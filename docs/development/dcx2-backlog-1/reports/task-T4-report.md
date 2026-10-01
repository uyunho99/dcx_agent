# T4 implementation report

Status: COMPLETE — T4 implemented; full frontend tests, lint, and TypeScript checks pass. No commit created.

## Scope and behavior

- `CoveragePanel.tsx`: pure interpretation/evidence/metric builders; autocomplete provenance and rank weighting; partial/total failure copy; rank bands with `—` for empty bands; no-volume M7; source-specific table headings and empty copy. Loading has a polite live announcement, disabled/loading refresh button, and retained metrics at reduced opacity.
- `CoveragePanel.test.ts`: offline SSR assertions using the real design-system components, pure metric assertions, fake-timer polling tests, cancellation protection, and mocked refresh request. Searchad and R-114 unconnected copy are covered.
- `types.ts`: coverage contract fields, nullable M2, rank bands and typed query/rank tuples. API module re-exports the type to preserve existing imports.
- `api/keywords.ts`: explicit recalculation posts `refresh=true` while retaining version routing.
- `pipeline/keywords/page.tsx`: poll loading coverage every 3 seconds; stop on a terminal status and cancel on cleanup/version change. Disable all R3 generate/retry/regenerate entry points and R2 → R3 next action, with an action-level guard and exact notice. Existing awaited reload after refresh is retained.
- Did not edit `StepBar.tsx`, `layout.tsx`, `completedThrough.ts`, backend files, or other parallel-task changes.

## RED evidence (before implementation)

Command: `npm --prefix frontend test -- --run CoveragePanel`

The initial run failed: 10 failed, 5 passed. New failures covered autocomplete evidence, rank bands, unavailable/loading copy, empty-table copy, polling/cancellation and `refresh=true`; existing compatibility checks passed.

```text
❯ src/components/keywords/CoveragePanel.test.ts (15 tests | 10 failed) 23ms
   ✓ preserves R-114 unconnected copy with humanQueries=%j 4ms
   ✓ preserves R-114 unconnected copy with humanQueries=undefined 0ms
   ✓ preserves round interpretation for connected 0ms
   ✓ preserves round interpretation for failed 0ms
   ✓ preserves round interpretation for undefined 0ms
   × renders autocomplete insight, evidence and partial failures 12ms
     → expected '<div class="kw-coverage"><div class="…' to contain '사람 검색어'
   × shows rank bands with an em dash for an empty band 0ms
     → (0 , coverageMetrics) is not a function
   × explains unavailable autocomplete and failed seeds 2ms
     → expected '<div class="kw-coverage"><div class="…' to contain '네이버 자동완성을 받지 못해 커버리지를 계산할 수 없습니다. 판정은…'
   × announces loading, disables refresh and dims retained metrics 2ms
     → expected '<div class="kw-coverage"><div class="…' to contain 'aria-live="polite">네이버 자동완성에서 사람 검색어를…'
   × distinguishes empty tables by source and preserves searchad metrics 1ms
     → expected '<div class="kw-coverage"><div class="…' to contain '자동완성 검색어를 모두 덮고 있습니다.'
   × polls every 3 seconds and stops on connected 1ms
     → (0 , startCoveragePolling) is not a function
   × polls every 3 seconds and stops on unavailable 0ms
     → (0 , startCoveragePolling) is not a function
   × polls every 3 seconds and stops on unconnected 0ms
     → (0 , startCoveragePolling) is not a function
   × cancels in-flight coverage polling without applying stale results 0ms
     → (0 , startCoveragePolling) is not a function
   × explicit recalculation sends refresh=true and keeps the version 0ms
     → expected '/keywords/session/coverage?version=v1' to contain '/keywords/session/coverage?refresh=tr…'
```

## GREEN evidence

Targeted command: `npm --prefix frontend test -- --run CoveragePanel`

```text
Test Files  1 passed (1)
     Tests  15 passed (15)
```

Required full command: `npm --prefix frontend test -- --run`

```text
Test Files  44 passed (44)
      Tests  274 passed (274)
   Start at  16:02:21
   Duration  1.51s (transform 785ms, setup 0ms, collect 3.00s, tests 486ms, environment 6ms, prepare 2.28s)
```

Required lint command: `npm --prefix frontend run lint` — PASS, no diagnostics.

Additional validation: `cd frontend && npx tsc --noEmit --incremental false` — exit 0; `git diff --check` — exit 0.

## Ambiguities and choices

- Coverage was originally declared in the API module, with no coverage declaration in `types.ts`. The canonical contract now lives in the authorized `types.ts` and is re-exported from the API module; existing imports remain compatible. Optional fields and the existing string status accommodate legacy responses including `failed`.
- The approximately 20-second text is an estimate, not a client timeout. Polling continues until status leaves `loading`; the contract's two-minute stale-loading conversion is owned by T3. The frontend does not infer failure or unlock R3 from elapsed wall time.
- “All autocomplete queries covered” is shown only for connected autocomplete with an empty missing table, so loading/failure does not falsely claim complete coverage.
- M1's autocomplete label is `① 순위 가중`, consistent with the contracted weighting. Searchad retains its original labels and behavior.
- Read-only views may issue GET polling for loading coverage; polling performs no refresh mutation.
- The polling helper stays in the authorized coverage component module to test timer/cancellation behavior without adding files outside T4 ownership.

## Verification limits

No live backend integration or browser QA was performed while T3 is being implemented in parallel. Tests use the brief's contract fixtures, SSR markup, fake timers, and mocked fetch. R3 page wiring was reviewed in the diff and type-checked; polling behavior and card accessibility markup are automated tests.
