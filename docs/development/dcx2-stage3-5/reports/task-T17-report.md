# T17 report — DCX2 stage 3 전처리 화면

## Status

Implemented within T17 ownership. Automated verification passes. Browser QA and commit are left to the controller as instructed; neither was performed.

## Requirements read

- `.superpowers/sdd/03-plan/task-T17-brief.md` (read first)
- Plan repository `docs/development/dcx2-stage3-5/02-design-r2.md`, especially §§3.1–3.6, 9, 9.1, 10
- Plan repository `docs/development/dcx2-stage3-5/mockups/index.html`, screen `s1`
- Plan repository `03-plan.md`, QA-P acceptance scenario
- Existing T16 prep API/types, version/session APIs, design system, and backend preparation contracts/defaults

## Owned files changed

- Modified `frontend/src/app/pipeline/preprocess/page.tsx`
- Added `frontend/src/components/prep/PrepScreen.tsx`
- Added `frontend/src/components/prep/PrepSettings.tsx`
- Added `frontend/src/components/prep/PrepResult.tsx`
- Added `frontend/src/components/prep/prep.css`
- Added `frontend/src/components/prep/prep.ts`
- Added `frontend/src/components/prep/prep.test.ts`
- Added `frontend/src/components/prep/workflow.ts`
- Added `frontend/src/components/prep/workflow.test.ts`
- Added this requested report

No shared API, shared type, label, known, layout, or backend files were edited by T17. Other concurrent tasks' modifications were left intact. No commits, staging, or browser screenshots.

## Behavior implemented

### Settings and layout

- Replaced legacy preprocess/save-session flow with the stage-3 screen and existing Person A tokens/components.
- Exact title and explanation from s1; section title uses 24/34/700, result headline uses insight typography.
- Two-column 8:4 layout, collapsing to one column on smaller widths.
- Rule editors for newline-separated advertising words and excluded sources, and integer minimum body length (default 10, zero allowed).
- Crawl rules are inherited; persisted prep config overrides them; a saved prep draft overrides config. Empty lists and zero remain intentional values.
- Five keyboard-accessible channel tabs, default/custom origin, phrase addition/deletion, counts, empty states, and channel replacement totals.
- Local default boilerplate mirrors `backend/app/prep/boilerplate.v1.json` verbatim, rather than using mockup fixture phrases as production defaults.
- Fixed configuration defaults: Kiwi; NNG/NNP/VV/VA/XR; voyage-4; 1024 dimensions. Fake embedder selector is gated by the existing `INTERNAL_TOOLS` constant.
- Output explanation identifies cleaned text, morphology tokens, and embeddings; reuse explanation is visible before execution.
- Results appear above settings; completed settings collapse under “규칙 수정하고 다시 실행”.
- Exactly one blue primary action: execution before a usable result; “라벨링으로” after a nonempty result, with a secondary rerun action. Empty results keep rerun as the primary action.

### API and persistence

- Restores selected-version settings with `getVersionSession`, and fetches `getPrepStatus` on entry, including direct reload during a job.
- All prep mutations/status calls and session patches carry the selected version.
- Draft save uses `PATCH /session` with `drafts.prep.config` only.
- Execution validates the minimum, saves through `savePrepConfig`, runs through `runPrep`, then clears the draft using `PATCH /session`.
- A failure clearing a draft does not conceal an accepted/running job.
- If config saving succeeds but starting the run fails, status is reloaded so an invalidated previous result is not offered for navigation.
- No `/save-session`, `saveSession`, or legacy preprocess APIs remain in T17 files.
- Advancing patches only `step: 'labeling'`, updates the local session step, then navigates after persistence succeeds.
- Mutation lock prevents rapid duplicate submissions; controls are disabled during mutations and active jobs.
- Dirty-provider registration and beforeunload handling protect unsaved settings; failures retain current inputs.
- Legacy sessions cannot edit or run new preparation. Missing session/collection states provide navigation actions.

### Run/results states

- Loading placeholder and settings-fetch retry.
- Filter → token → embedding sequence with real backend progress, polling every three seconds during running/paused states.
- Polling errors are visible, auto-retry, and expose manual retry; cleanup ignores results after unmount/version changes.
- Interrupted runs offer “이어서 진행”; the same config allows backend shard reuse.
- Failed and cancelled states expose retry; disconnected embedding and Kiwi-specific error kinds use the specified Korean copy.
- Zero-document message is verbatim: “규칙을 통과한 문서가 없습니다. 광고어와 길이 규칙을 확인하세요.” No next-stage action for an empty result.
- Result interpretation, original/after counts, rule removal bars, replacement/token/embedding totals, collection/model/date metadata.
- Zero-vector failures explicitly say they are excluded from search/training.
- Cache reuse shows “같은 규칙의 결과를 그대로 씁니다” with the actual creation date when available. Reused responses and persisted done results without a run ID are recognized.
- Raw prepKey is internal-tools-only.

## Test-first evidence

Both logic test files were created and run before their implementation files: the first runs failed with the expected missing-module errors. A later paused-versus-interrupted regression test was also run red before its fix.

13 local tests cover:

1. Inherited crawl rules and exact config defaults.
2. Draft priority and preservation of explicit empty lists/zero.
3. Restoring actual running config instead of a draft.
4. Newline normalization without splitting commas inside phrases/source names.
5. Suppression of stale result data while a run is active.
6. Empty/partial/missing result handling and next-stage availability.
7. Interrupted-only resume availability.
8. Real phase/shard information without fabricated intermediate completion.
9. Prior measured counts and float16 vector-storage estimate (1024 × 2 bytes/document).
10. Config → run → draft-clear ordering and immediate reused result preservation.
11. No run after config-save failure.
12. Accepted job stays available after draft-clear failure.
13. Invalid minimum lengths are rejected before any network request.

## Final verification

All checks ran against the shared worktree, including the other tasks' files as they existed at verification time.

| Check | Result |
| --- | --- |
| `npm --prefix frontend test -- --run` | PASS: 32 files, 174 tests, including all 13 T17 tests |
| `npm --prefix frontend run lint` | PASS, no diagnostics |
| `npx --prefix frontend next build --webpack` | PASS from the `frontend` working directory; TypeScript, static generation (14/14), and route build completed |
| Owned-file `git diff --check` | PASS |
| Search for legacy save/preprocess calls in T17 files | No matches |

Build used webpack, not Turbopack. Node emitted an existing `module.register()` deprecation warning; it did not fail any check. No browser QA was run.

## API limitations and controller QA notes

- The current prep API has no pre-run pass-count/time estimate. The estimate card shows real collected document counts where available; after a result it uses the last run's counts and calculates vector-only storage using float16. It explicitly says the embedding time estimate is unavailable. Mockup figures (412,330 / 318,204 / 2 hours) are not fabricated as live values.
- Replacement counts are channel-level in `stage_3.json`, not phrase-level. The table includes the requested count column but marks it “채널별 집계” after a run and shows the real channel total below it.
- Current backend heartbeats expose embedding shard progress, not distinct filter/token completion. Until phase or shard data exists, the UI displays the full processing sequence without claiming those steps are complete.
- The backend emits a generic prep failure for some failures (including missing Kiwi). The screen handles the specific Kiwi kind if supplied, but cannot reliably infer it from a generic backend error.
- The supplied API has no paused-prep resume endpoint, and POST run returns an already-paused worker unchanged. Paused state stays visible and polls; it does not offer a nonfunctional resume action. Interrupted work can be restarted through the existing run endpoint.
- Local boilerplate defaults should be kept aligned if the backend versioned defaults change; there is no read-defaults prep API to fetch them independently.

Controller QA-P: add one channel phrase → save/reload if desired → run → verify result and rule bars → create a new version “3단계부터 다시” through existing version controls → execute unchanged settings → verify the reuse message and actual date. Also check zero-document output, partial embedding failure, disconnected embedding, interrupted continuation, keyboard tabs, and collapsed settings at the target viewport.
