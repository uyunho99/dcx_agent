# Task T14 report

- status: implemented_with_concerns
- executor: codex
- branch: feature/dcx2-stage6-8
- Scope: stage 6 bundle 1 clustering screen. No git add/commit, subagents, dependency installation, or external network calls.

## Files

- `frontend/src/app/pipeline/clustering/page.tsx`: route sessions with `prep.derivedRef` to SegmentScreen; retain legacy results with disabled writes and a read-only notice.
- `frontend/src/components/segment/SegmentScreen.tsx`: stage6 version wrapper/action, layer gates, polling, progress, confirmation APIs, draft persistence, k reset dialog, errors/refresh, and disabled evidence action.
- `frontend/src/components/segment/ClusterLayer.tsx`: names, representatives, quality, channels, keywords, and split/merge request notes.
- `frontend/src/components/segment/PersonaLayer.tsx`: cluster/Persona selection, Desire/Goal editing, similarity warning, community warning, unstable flag, optional hint, and representative text.
- `frontend/src/components/segment/ContextLayer.tsx`: all Contexts for the selected Persona, individual/bulk confirmation, counter/few-docs/granularity warnings, and empty goal/constraint ratio.
- `frontend/src/components/segment/WordNetwork.tsx`: SNAGraph adapter with copied inputs, escaped tooltip labels, community colors, and textual community lists.
- `frontend/src/app/pipeline/clustering/page.test.ts`: 20 offline tests.
- This report.

No shared version type change was necessary: the committed `Stage` already accepts `stage6`. The actual exports in `StageVersion.tsx` are `VersionStage` and `StageVersionAction`; those are reused. `VersionRouteBoundary` is unchanged, preserving the previous-version information card (D-238). Global sidebar changes (D-219) are outside the owned files and were not made.

## RED → GREEN → refactor

1. Added the initial eight screen/component requirements tests before creating the components. `npm --prefix frontend test -- clustering` failed because SegmentScreen did not exist (RED).
2. Implemented the owned components using the committed API, view helpers, ds components, tabs, quality/channel/chart components, SNAGraph, and polling hook. Expanded interaction coverage for confirmation counts, stale-run failures, reset payload, and Persona bulk confirmation. The scoped suite reached GREEN.
3. Added a regression test for a failed PATCH after a successful confirmation. It failed because the edit was cleared too early (expected `저장할 이름`, received undefined). Moved edit clearing until the save/status sequence succeeds; the test passed.
4. Refactored the status handling to reject obsolete requests, serialize draft writes before confirmation/re-run, stop/restart polling around review/run states, and preserve inputs on failure. Added keyboard focus/return/Escape behavior to the reset dialog, and explicit cluster selection in 6-B.

Final scoped tests cover:

- New/legacy routing and legacy read-only controls.
- Initial single primary action, aria-live running steps, disabled run/reset actions.
- 6-A confirmation payload with run, updated 4/5 progress, and locked Persona tab.
- Blank Desire, similarity copy, Persona edits, and individual Context edits.
- Persona-specific bulk payload, counter warning, six-Context granularity badge.
- Disabled evidence action after all confirmations with the exact bundle tooltip.
- Changing k to 7, explicit confirmation copy, and `confirmReset: true`.
- Input retention for API failures, stale-run refresh affordance, and post-confirm draft cleanup failure.
- PATCH-only `drafts.segment` persistence and rejection of previous-run drafts.
- One-community, few-docs, and failed-draft copy from s8.

## Verification

- `npm --prefix frontend test -- clustering`: **20/20 passed** on the final test file.
- `npm --prefix frontend run lint`: **passed, no warnings** on the final files.
- `npm --prefix frontend test`: **51 files / 403 tests passed**, run exactly once as requested. This full run preceded the final localized draft-cleanup regression fix and added tests; the affected clustering suite was rerun afterward and passed 20/20.
- `npm --prefix frontend run build`: attempted; the default Turbopack build remained at “Creating an optimized production build” without further output for several minutes and was interrupted. No successful default-Turbopack result is claimed.
- `npm --prefix frontend run build -- --webpack`: **passed** after the final application changes, including TypeScript and all 14 static pages. The package/config was not changed.
- `tsc --noEmit`: passed during implementation; the final webpack build also passed TypeScript checking.
- `git diff --check`: passed.

## Self-review / mockup coverage

- **s1 / 6-A:** editable cluster names, confirmed state, quality metrics, representative text, keyword/channel details, k suggestion chart, explicit reset, and request notes. At most one layer confirmation is primary.
- **s2 / 6-B:** cluster selection and its Persona list, force network and text alternative, centrality, name/Desire/1–3 Goals, similar-Desire explanation, individual confirmation.
- **s3 / 6-C:** persistent left Persona list with per-Persona counts; all selected Persona Contexts expanded; individual secondary confirmations plus one primary bulk confirmation; counter/few-docs/granularity warnings; evidence action stays disabled.
- **s8 / stage-six states:** loading, seven running steps with text status, no-document result, one-community warning, failed drafts, backend reasons, interrupted/failed/paused continue action, save failure with retained input, stale-run message and refresh.
- **D-238:** no historical live editor bypass was added.
- **D-239:** writes and drafts carry run; mismatched list generations are rejected; old drafts are discarded; server messages are shown with refresh.
- Existing design tokens/ds classes and `minmax(0, …)` grids are used; inputs and long names can wrap within the available desktop content width. Tabs/buttons are native keyboard controls; progress is aria-live; flags have text labels. A real 1024px browser/screenshot QA was not performed, so pixel fidelity/overflow is not claimed as visually verified.
- No bundle-two emerging/lexical-surprise behavior, active evidence action, or new whole-session save was introduced.

## Concerns

1. Default Turbopack build did not finish in this sandbox. Webpack production build passed; controller should verify the prescribed default build in its normal environment.
2. Existing backend contract inconsistency: `POST /segment/{sid}/run` rejects an existing result without `confirmReset`, even for an interrupted run; the pipeline itself supports checkpoint resume without reset. The screen offers “이어서 진행” using the committed start API and displays that backend message if rejected. A separate explicitly confirmed reset is available. Fixing true checkpoint resume requires a backend/controller decision outside T14 ownership.
3. Browser visual QA at 1024px and live fake-backend end-to-end testing remain unperformed; all tests were offline mocked component/hook tests.

## Fix round 1

- Status: implemented; all nine review findings addressed. No git add/commit, subagents, dependency changes, or out-of-scope application edits.
- Files: `SegmentScreen.tsx`, `PersonaLayer.tsx`, `segmentView.ts`, their scoped tests (`clustering/page.test.ts`, `segmentView.test.ts`), and the minimal optional banner prop in `versions/StageVersion.tsx`.

### Changes and covering tests

1. Read the authoritative versioned session with `getVersionSession(sid, version)` on mount before enabling edits. Restore only `drafts.segment` matching the current generation. The regression saves a typed draft, unmounts, and remounts with a stale draft prop; the server draft wins. A separate regression rejects an old-generation server draft.
2. Export shared segment error messages and omit “입력은 유지됩니다.” for `stale_run`. The stale-error → refresh → new-generation test verifies edits become `{}`. A successful status read does not silently clear a stale write error.
3. Preserve the mounted editor and lists while refreshing after confirmation; load the status snapshot once, and ignore subsequent cached draft prop updates. Preserve disclosure DOM nodes instead of replacing them with a loading card. Capture the focused control before saving and restore focus afterward, preferring the forward button when the layer is complete. Tests cover editor continuity, one reload per confirmation, and focus restoration to the forward control.
4. Initialize k from the suggestion only on a new run generation. Tests cover choosing 7, confirming without losing it, and adopting a new suggestion after the generation changes.
5. `VersionStage` now has optional `showBanner = true`; only SegmentScreen sets it false because its route boundary already renders the banner. Readonly fieldset behavior remains unchanged. A screen regression checks the opt-out; the existing version/shell tests passed in the full suite.
6. Move running `aria-live` to one short line, e.g. “L3 · Context 진행 중 58%”. The test asserts one live region with exactly that text; the seven-step list is outside it.
7. Separate recoverable poll errors from write/load errors and clear the poll error on the next successful status request. Covered by failed-then-successful fetcher calls.
8. Add primary “6-B로 →” and “6-C로 →” actions after each corresponding layer is fully confirmed, with no pending edits. Demote Persona confirmation when the forward action is primary. The regression expands both layer components, counts exactly one primary, and exercises both transitions.
9. Keep “이어서 진행” for interrupted/failed runs and POST `{}` without `confirmReset`; generation rotation clears old edits. Match the exported running-conflict message preserved by the shared API wrapper, show it as a notice, fetch the current worker status, and resume polling. Running and paused workers both stay in the progress view. Tests cover interrupted/failed resume, both conflict states, running error mapping, and the real API wrapper with an offline 409 response. The previous report's backend-resume concern is resolved by T10 plus these tests.

### RED → GREEN and verification

- Tests were added before implementation. Initial `npm --prefix frontend test -- clustering`: **9 failed / 22 passed (31)**, reproducing stale remount drafts, stale retention copy, editor teardown/reload/k behavior, sticky poll errors, oversized live announcements, duplicate-banner configuration, missing forward actions, and running/paused conflict handling. Existing interrupted/failed resume payload tests were already green.
- Initial `npm --prefix frontend test -- segmentView`: **1 failed / 14 passed (15)**, missing the running-kind message mapping.
- After implementation and additional generation/focus/error-isolation coverage:
  - `npm --prefix frontend test -- clustering`: **34/34 passed**.
  - `npm --prefix frontend test -- segmentView`: **16/16 passed**.
  - `npm --prefix frontend run lint`: **exit 0, no warnings**.
  - `npm --prefix frontend test`: **51 files / 423 tests passed**, executed exactly once for this fix round, after the final application changes.
  - `npm --prefix frontend run build -- --webpack`: **exit 0; compilation, TypeScript, and 14/14 static pages passed**. Used webpack as requested because default Turbopack can hang in this sandbox; did not attempt the default build this round.
  - `git diff --check`: **exit 0**.
- Tests/build emitted the existing Node `DEP0205` module.register deprecation notice; no test or build failures remain.

### Concerns

- No browser visual/screen-reader QA or live-backend end-to-end run was performed. Editor continuity and focus behavior are covered by the existing hook/element test harness, not a real-browser DOM test. No known implementation blockers remain.
