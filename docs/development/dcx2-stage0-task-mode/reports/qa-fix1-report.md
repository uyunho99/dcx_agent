# QA fix round 1 report

Date: 2026-10-02
Branch: `feature/dcx2-stage0-task-mode`
Design authority: `docs/development/dcx2-stage0-task-mode/02-design.md`, section 5.2.

## ISSUE-001 — root cause

`SaveBar` renders its Save button with `disabled={!valid}` (`frontend/src/components/SaveBar.tsx:19`). The start page passed the actual validation result, disabling Save whenever a field was invalid. The disabled native button never invoked `onSave`, so `persist()` never reached its invalid-field query, scrolling, or focus. The error text was already rendered by validation on each render; clicking Save did not produce it.

The form ref encloses the fields, and invalid inputs and fieldsets are already marked in the committed DOM. Fieldsets have `tabIndex={-1}`. This is not a missing-ref or deferred-error-render problem, and no timing workaround or pure helper is needed.

## Changes

Only `frontend/src/app/pipeline/start/page.tsx` was changed, plus this requested report.

- Lines 291–292: pass `valid={true}` to SaveBar with an explanatory comment, keeping Save actionable so `persist(false)` can report invalid fields. The actual `valid` guard in `persist()` remains in force and prevents invalid API writes. Busy state still disables Save through its loading prop; historical versions remain protected by the existing disabled ancestor fieldset.
- Lines 154–158: retain the first `[aria-invalid="true"]` lookup and `scrollIntoView({block: "center"})`; use `focus({preventScroll: true})` so focusing cannot override the requested centered position. This generic lookup supports both native inputs and focusable fieldsets. Save and “키워드 생성 시작하기” both use this same validation branch, including repeated failed attempts. Draft behavior is unchanged.
- Line 272: replace the persona input/button flex row with a responsive grid, bottom-align its children, and reset the direct `.ds-field` bottom margin. The shared `.ds-field` style has a 20px bottom margin unless it is the last child; the following button caused that margin to offset the persona input. `sm:grid-cols-[minmax(0,1fr)_auto]` keeps input and button on one row at desktop widths and stacks them on narrow screens.

No helper was added; `startForm.ts` and shared components were not changed. No agents, staging, or commits were used.

## Verification

All three required commands completed with exit code 0. Full captured output follows. `git diff --check` also passed with no output.

Browser regression was not rerun: the connected UI tool inventory returned no available browsers. Input/fieldset focus, viewport centering, and the 1360px/375px layouts have code-level review only; the unit suite and build do not establish browser geometry. The build emitted Node warning DEP0205 about `module.register()` deprecation but completed successfully. ISSUE-003 remains outside this task's scope.

### `npm --prefix frontend run lint`

Exit code: 0

```text

> frontend@0.1.0 lint
> eslint

```

### `npm --prefix frontend test`

Exit code: 0

```text

> frontend@0.1.0 test
> vitest run


 RUN  v3.2.7 /Users/persona1/Desktop/dcx_agent-stage0-task-mode/frontend

(node:9706) [DEP0205] DeprecationWarning: `module.register()` is deprecated. Use `module.registerHooks()` instead.
(Use `node --trace-deprecation ...` to show where the warning was created)
 ✓ src/components/train/trainingView.test.ts (20 tests) 19ms
 ✓ src/components/label/workerControls.test.ts (3 tests) 23ms
 ✓ src/app/pipeline/training/page.test.ts (6 tests) 36ms
 ✓ src/components/known/KnownInsightsDrawer.test.ts (4 tests) 22ms
 ✓ src/components/prep/PrepScreen.test.ts (6 tests) 26ms
 ✓ src/lib/logic/completedThrough.test.ts (30 tests) 19ms
 ✓ src/lib/logic/nowCard.test.ts (7 tests) 15ms
 ✓ src/components/label/QueueCard.test.ts (5 tests) 28ms
 ✓ src/lib/logic/qaFix.test.ts (9 tests) 13ms
 ✓ src/lib/logic/finishPartial.test.ts (2 tests) 19ms
 ✓ src/components/versions/VersionProvider.test.ts (2 tests) 9ms
 ✓ src/lib/logic/compareView.test.ts (3 tests) 8ms
 ✓ src/components/browserQa.test.ts (7 tests) 81ms
 ✓ src/app/pipeline/labeling/page.test.ts (2 tests) 9ms
 ✓ src/components/keywords/CoveragePanel.test.ts (28 tests) 96ms
 ✓ src/components/chat-flow.test.ts (2 tests) 8ms
 ✓ src/app/pipeline/clustering/page.test.ts (3 tests) 6ms
 ✓ src/lib/logic/finalFix.test.ts (10 tests) 7ms
 ✓ src/lib/logic/crawlLoad.test.ts (3 tests) 5ms
 ✓ src/lib/api/label.test.ts (10 tests) 16ms
 ✓ src/lib/logic/actionQueue.test.ts (2 tests) 4ms
 ✓ src/lib/logic/mutationContract.test.ts (4 tests) 6ms
 ✓ src/components/ds/choiceCards.test.ts (13 tests) 15ms
 ✓ src/components/prep/workflow.test.ts (4 tests) 10ms
 ✓ src/lib/logic/nextTrapIndex.test.ts (3 tests) 1ms
 ✓ src/lib/refreshSessionAfterStage.test.ts (4 tests) 6ms
 ✓ src/lib/logic/labelKeys.test.ts (5 tests) 6ms
 ✓ src/lib/logic/josa.test.ts (22 tests) 29ms
 ✓ src/lib/logic/filterKeywords.test.ts (3 tests) 4ms
 ✓ src/lib/logic/startForm.test.ts (36 tests) 4ms
 ✓ src/components/prep/prep.test.ts (11 tests) 5ms
 ✓ src/lib/logic/restartVersion.test.ts (6 tests) 7ms
 ✓ src/lib/api/errors.test.ts (21 tests) 9ms
 ✓ src/components/label/useLabelSeen.test.ts (1 test) 4ms
 ✓ src/lib/logic/crawlConfig.test.ts (4 tests) 6ms
 ✓ src/lib/logic/versionSelection.test.ts (4 tests) 3ms
 ✓ src/components/label/queueView.test.ts (3 tests) 2ms
 ✓ src/components/versions/versions.test.ts (2 tests) 5ms
 ✓ src/lib/logic/isDirty.test.ts (4 tests) 8ms
 ✓ src/lib/logic/channelBars.test.ts (2 tests) 1ms
 ✓ src/lib/logic/nextFocus.test.ts (3 tests) 3ms
 ✓ src/lib/logic/roundUi.test.ts (8 tests) 4ms
 ✓ src/components/shell.test.ts (11 tests) 2ms
 ✓ src/lib/logic/smoke.test.ts (1 test) 2ms
 ✓ src/components/versions/useStageCompletionRefresh.test.ts (5 tests) 2ms
 ✓ src/lib/logic/finalW4.test.ts (4 tests) 4ms
 ✓ src/lib/logic/keywordDraft.test.ts (1 test) 1ms
 ✓ src/lib/logic/reviewKeywords.test.ts (1 test) 4ms
 ✓ src/lib/logic/crawlWindow.test.ts (3 tests) 3ms
 ✓ src/lib/logic/keywordKeys.test.ts (3 tests) 4ms

 Test Files  50 passed (50)
      Tests  356 passed (356)
   Start at  15:04:14
   Duration  1.99s (transform 1.06s, setup 0ms, collect 4.18s, tests 630ms, environment 13ms, prepare 2.65s)

```

### `npm --prefix frontend run build -- --webpack`

Exit code: 0

```text

> frontend@0.1.0 build
> next build --webpack

▲ Next.js 16.1.6 (webpack)
- Environments: .env.production

  Creating an optimized production build ...
(node:9856) [DEP0205] DeprecationWarning: `module.register()` is deprecated. Use `module.registerHooks()` instead.
(Use `node --trace-deprecation ...` to show where the warning was created)
✓ Compiled successfully in 1416.0ms
  Running TypeScript ...
  Collecting page data using 9 workers ...
  Generating static pages using 9 workers (0/14) ...
  Generating static pages using 9 workers (3/14) 
  Generating static pages using 9 workers (6/14) 
  Generating static pages using 9 workers (10/14) 
✓ Generating static pages using 9 workers (14/14) in 155.9ms
  Finalizing page optimization ...
  Collecting build traces ...

Route (app)
┌ ○ /
├ ○ /_not-found
├ ○ /insights
├ ○ /pipeline/clustering
├ ○ /pipeline/compare
├ ○ /pipeline/crawling
├ ○ /pipeline/keywords
├ ○ /pipeline/labeling
├ ○ /pipeline/personas
├ ○ /pipeline/preprocess
├ ○ /pipeline/start
└ ○ /pipeline/training


○  (Static)  prerendered as static content

```
