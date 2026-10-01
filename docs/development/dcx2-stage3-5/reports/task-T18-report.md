# T18 implementation report

## Scope

Implemented DCX2 stage 4 labeling in the assigned workspace. Read the T18 brief first, then design r2 sections 4.11–4.12, the supplied labeling mockups, and the committed T16 API, logic, and components. No AGENTS.md files were found in the workspace.

Source files changed by this task only:

- `frontend/src/app/pipeline/labeling/page.tsx`
- `frontend/src/components/label/Overview.tsx` (new)
- `frontend/src/components/label/Queue.tsx` (new)
- `frontend/src/components/label/Audit.tsx` (new)

This report is the explicitly requested additional artifact. Existing T16 files and other agents' files were not edited. No commits were made.

## Implementation

### Page and overview

- Replaced the legacy sample/whole-session-save screen with three tabs: 개요, 검수 큐, 감사. Initial tab is 개요.
- Reads version-scoped overview data immediately and every five seconds, with stale-response cleanup, visible errors, retry, and session/version keyed remounts.
- Reuses `pickNowCard` for the committed priority order and next action. Shows changes since last visit, mismatch rate, accepted counts, queue counts and estimated review time.
- Before starting: LLM/model choice, compatible-model selector, one estimate line, and one primary “라벨링 시작” button. Models marked unselectable by the server remain disabled with their reason. Model choice is disabled when no selectable model exists.
- Start persists mode through `setLabelMode`, then calls `startLabel`. A local request lock prevents duplicate clicks.
- Once started, a mode-lock badge replaces selection. Composes the existing “4단계부터 다시” version control.
- Reuses `LabelerProgress`, `LevelBadge`, and `KappaTable`. Shows worker pause/resume, estimated finish where seconds are supplied, grade counts and audit-based performance.
- Overview polling never calls `seen`, and never uses whole-session save.

### Review queue

- Mounts only when the queue tab is open. Calls `markLabelSeen` once per opening of the writable queue tab; a ref guards React StrictMode effect replay. No retry or polling repeats that mutation. Audit/re-issue do not call it.
- Uses `getNextLabel` to fetch one document. Skip forwards the shared QueueCard's `item.cursor` unchanged as `after`; ordinary next resets the cursor. An empty cursor tail can be restarted from the beginning.
- Composes T16 `QueueCard` without modification for tags, rule-preview API, immediate per-item submit/save, post-submit comparisons, error preservation, and document focus.
- Shows remaining count/time, reason counts, keyboard scope/help, loading, error/retry and empty states.
- No separate save button. No client grade calculation.

### Audit

- Displays round list, per-round sample counts/grade κ and textual κ trend; explicit insufficient-sample and κ < 0.75 messaging.
- Composes `createAudit` for manual 50-item rounds and shared QueueCard for independent audit and re-issue review. Supports per-round and all-pending-round selection.
- States the automatic schedule exactly: first at 1,000 accepted items, then 50 every 10,000; re-issue two previous audit documents per round.
- Shows self-consistency, definition-check warning, and first-round completion guidance after 50 judgments.
- Displays the one-line context and q1 tag-definition wording beside the independent card. Definition text mirrors the backend's existing q1 JSON; rules still run exclusively through the server preview API.
- No tau, alpha, calibration or AlphaPanel UI.

## Tests and QA evidence

No new standalone logic functions were introduced: this change composes existing tested logic/API clients and adds React view state, effects and event handlers. Existing T16 Vitest tests cover now-card priority, keyboard focus scope, version encoding, `seen` POST and opaque skip cursor forwarding. Those files were not modified. No new test files were created outside the four-file ownership scope.

Code/contract review against QA-L1–L6:

| Case | Evidence |
| --- | --- |
| QA-L1 | Start-only primary action, mode/start API sequence, per-worker progress and locked-mode badge. |
| QA-L2 | Unmodified QueueCard uses tested `keyAction`; input/panel/popover exclusions, polite grade announcement and source focus remain intact. |
| QA-L3 | Shared submit API writes each item immediately; reopening reads next from server, not browser-only labels. Actual server durability remains the backend test contract. |
| QA-L4 | Five-second overview refresh feeds summary, progress, review estimates and audit sample/performance tables. |
| QA-L5 | Shared QueueCard hides AI votes until submit resolves, then displays comparisons. |
| QA-L6 | Backend definitionCheck drives the warning and tested now-card priority; audit shows round κ values and first-round guidance. |

No browser screenshots or browser interaction QA were performed. These are code/contract checks, not claims of an executed end-to-end browser journey.

## Verification

- `npm --prefix frontend test -- --run`: initial run passed, 31 files / 169 tests. A subsequent run encountered an in-progress parallel-task test (`prep/workflow.test.ts`) referencing a not-yet-created `./workflow` module; 169 existing tests still passed. Final recheck recorded below.
- `npm --prefix frontend run lint`: passed, no lint errors.
- Requested literal `npx --prefix frontend next build --webpack`: failed from repository root because npm's prefix selects the executable but Next still searches the current directory for app/pages.
- Corrected project-path invocation `npx --prefix frontend next build frontend --webpack`: passed webpack compilation, TypeScript and static page generation (14 pages).
- `git diff --check`: passed.
- Only warning seen in successful test/build output was the existing Node `module.register()` deprecation warning.

## Integration limits

- The committed backend estimate returns `seconds` and `jevTokens`, not monetary cost. UI exposes the supplied token estimate and explicitly says the Jev monetary estimate is not provided; no price is invented or calculated on the frontend.
- Historical-route gating and version creation restrictions remain owned by the existing version components/server. The new components additionally accept/read readonly state and suppress mutation controls/calls.
- Tag definitions are a static mirror of q1 because the committed frontend contract has no definition-edit/read API. The screen supplies the requested definition guidance and existing new-version control; it does not introduce a new definition persistence contract.
- Parallel tasks have unrelated working-tree changes. They were preserved and were included in whole-frontend verification as present at execution time.

### Final test recheck

After the parallel prep task created `workflow.ts`, reran the full required Vitest command: **32 test files / 173 tests passed**, exit 0. No changes to that task's files were needed. The temporary missing-module failure is resolved. T18's final source also passed lint and the corrected webpack build invocation above.
