# Task T4 report

Status: implemented within the owned files. No staging, commits, page edits, or agent delegation.

## Changes

- `frontend/src/lib/types.ts`: changed only `ProjectContext`. Added optional/null task mode and persona seeds, optional/null analysis goal, structured metrics, and positioning text fields with nullable server preset values. `schemaVersion` remains 1.
- `frontend/src/lib/logic/startForm.ts`: new explore defaults; legacy/mixed metric conversion; preservation of saved analysis goals and normalization of empty goals to null; raw-context detection; validation; exact research templates; positioning toggle/text/open helpers; persona addition and missing-dimension helpers. Merging clones saved optional values so callers cannot mutate the source draft accidentally. Persona and positioning text are trimmed and truncated to 40 Unicode code points.
- `frontend/src/lib/logic/startForm.test.ts`: 35 tests covering defaults, migration, validation, exact template text, Korean particles, positioning, persona limits/duplicates, and dimension order, alongside the existing next-step checks.
- `.superpowers/sdd/03-plan/task-T4-report.md`: this report.

## RED

Command: `npm --prefix frontend test -- src/lib/logic/startForm.test.ts`

Run before implementation or type changes. Exit 1: 26 failed, 9 passed, 35 total. Failures showed missing helper exports, absent task-mode/persona defaults, missing positioning text defaults, and unconverted legacy metrics. The existing next-step checks and null/missing-draft equality passed. These were the expected missing-contract failures.

## GREEN

Command: `npm --prefix frontend test`

Final result: exit 0, all 49 test files and all 342 tests passed; all 35 startForm tests passed.

The first implementation run passed 340 tests and exposed two test-table mistakes: Vitest unpacked array rows, passing undefined or an individual metric instead of the intended metric array. Changed those rows to objects containing `keyMetrics`, preserving the assertions and intended inputs, then reran the full suite successfully. No implementation behavior was weakened to satisfy that test error.

## Lint

Command: `npm --prefix frontend run lint`

Result: exit 0, no lint diagnostics.

## Build and type checking

Command: `npm --prefix frontend run build`

Turbopack remained at `Creating an optimized production build ...` for over two minutes with no further output. Build diagnostics still showed the compile stage. Stopped that attempt with Ctrl-C (exit 130); it did not produce a TypeScript result. The cause of the stall was not established.

Fallback command: `npm --prefix frontend run build -- --webpack`

Compilation succeeded in 3.2 seconds, then TypeScript failed (exit 1) at:

```text
./src/app/pipeline/start/page.tsx:34:276
Type error: 'context.analysisGoal' is possibly 'null' or 'undefined'.
Next.js build worker exited with code: 1 and signal: null
```

Additional diagnostic command, run from `frontend`: `./node_modules/.bin/tsc --noEmit --incremental false`

Exit 2; 15 diagnostics, all in unchanged `src/app/pipeline/start/page.tsx`, at lines 34, 75, 128–130, 147, and 148. They concern optional/null analysisGoal access and updates, structured metrics passed to the old string-list input, and nullable positioning preset values passed to string-only consumers. No diagnostics in the T4 implementation or tests. These are the anticipated integration changes assigned to T6; page.tsx was not modified.

`git diff --check` passed.

## Reasons for changed existing expectations

- The null/missing-draft test still compares against `emptyStartForm`; its assertion did not need textual changes, but its expected value now includes the required explore/persona/positioning defaults and omits analysisGoal.
- The partial-draft test now expects empty `priceText` and `marketText` alongside its preserved preset, matching the new four-field positioning default.
- The full legacy-form test now expects structured metrics and newly supplied taskMode/persona/positioning defaults instead of byte-for-byte input-object equality. All saved content, including analysisGoal and other optional fields, remains preserved. This is the required draft normalization, not a storage migration or change to backend Markdown compatibility.

## T6 helper contracts

- `validateStartForm(form)` returns `{ valid, errors }`, with errors keyed by ProjectContext fields. It validates the merged UI form; server legacy-context validation remains the backend's responsibility.
- `researchTemplates(taskMode, bk)` returns `{ id, title, text }[]`; templates 1–3 reproduce the current page strings and titles, including the existing `bk || "제품"` fallback and `josa()` behavior.
- `positioningOpen(taskMode, positioning)` checks both preset and text fields. Preset/text editing helpers return new positioning objects.
- `addPersonaSeed(items, input)` returns `{ items }` on success or `{ items, reason }` with `empty`, `duplicate`, or `limit` on rejection. Duplicate detection ignores whitespace after trimming/truncation; a new seed has `dimension: null`. No input array is mutated.
- `missingDimensions(items)` returns codes in social, taste, movement, bio order.
- Call `isPreTaskModeContext` on the raw saved context before `mergeStartForm` supplies explore defaults.

## Concerns

- Production build/type checking remains blocked by the expected T6 start-page integration. The default Turbopack build also stalled in this environment; the Webpack fallback reached and confirmed the expected type error.
- Vitest/build emitted Node's DEP0205 module.register deprecation warning; tests and lint still passed.
- No other known T4 concerns. Only the three owned source/test files and this report were edited; no backend or React page changes were made.
