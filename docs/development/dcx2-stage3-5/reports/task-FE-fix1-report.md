# FE fix 1 report — T17–T20

## Result and scope

Implemented the frontend review follow-ups in `task-FE-fix1.md`. Read the T17–T20 briefs, the relevant sections of the supplied `02-design-r2.md`, and mockup copy. Application and test edits are confined to `frontend/`; this requested report is the only edit outside that directory. No backend files were edited by this task, no files were staged, and no commit was created. Concurrent backend changes visible in git status were left alone.

## Changes

### T17 — preprocessing result

`frontend/src/components/prep/PrepResult.tsx` now uses the exact partial-failure sentence:

> 임베딩 실패 {N}건은 0벡터로 남기고 검색 · 학습에서 제외합니다.

The count retains `toLocaleString('ko-KR')` thousands separators and the sentence remains conditional on failures being present.

### T18 — labeling screen baseline

- Removed the seen mutation and its error state from `components/label/Queue.tsx`.
- Added `components/label/useLabelSeen.ts` and invoked it from the labeling screen, independently of the selected tab and overview polling.
- A screen-local ref set records each sid/version before posting, preventing repeated writes during rerenders and React StrictMode effect replay. Readonly views do not post. Opening the screen again after a genuine unmount creates a new visit baseline, as required by the screen-open semantics.
- A failed mutation is shown at screen level and is not retried by polling.
- Added `useLabelSeen.test.ts` covering readonly suppression, repeated effects, and distinct sid/version pairs.

### T19 — training

- The card count and empty state now share `overview.accepted`. The exact empty copy is `학습할 라벨이 없습니다. 라벨링을 먼저 끝내세요.` and the count label is `학습할 라벨`.
- Zero accepted labels disable training, but do not disable `모델 없이 내보내기`. Existing readonly, loading, error and in-flight mutation guards remain.
- Model creation dates use date-only `ko-KR` formatting, e.g. `2026. 10. 2.`. Missing/invalid dates display `—`.
- Training result evidence uses meaningful labels (`임베딩`, `규칙`, `질문`, `생성`) instead of empty label strings.
- Drift requires a current training model ID and divergence above 15%, and includes the measured percentage. For 18%, the sentence is `무작위 1% 재판정에서 등급이 18% 엇갈렸습니다. 이 도메인은 LLM 라벨로 다시 하거나 추가 학습하세요.`
- Polling schedules another request only while the returned status indicates active work. Idle/completed/failed work without an active worker stops polling. Successful start/retrain and the existing explicit load retry restart the read effect. Stale request generations cannot schedule further polling.
- Added helper tests for count selection, date formatting, drift gating and polling decisions, plus a fake-timer screen test covering empty export availability, idle polling termination, user-start resumption and completion termination.

### T20 — shell and chat

- Copied both supplied `/tmp/t20-tests/chat-flow.test.ts` and `shell.test.ts` into `frontend/src/components/`, beside the tested components. Replaced absolute machine paths with relative imports; retained their original test cases.
- Configured Vitest with a portable `@` alias and automatic JSX transform so those component tests run under the standard frontend test command.
- Server-provided nonempty activity labels now take precedence for every status, including non-running states. Added parameterized coverage.
- Chat without a sid uses the exact legacy failure text `오류가 발생했습니다.` and does not show the `다시 찾기` button. Its loading message is also generic. Session-backed search retains its search error/retry flow.
- Added a legacy chat failure regression test; the supplied question → Known Insight addition → filtered retry → filter-off flow still passes.

## Test-first evidence

Persisted the T20 tests and added logic regression tests before implementation. The initial full Vitest run was RED: 4 failed files, 9 failed tests and 181 passing tests (including a missing new hook module). Failures covered the new helper contracts, activity label precedence and legacy chat error behavior. Implemented the fixes, then added the screen-level fake-timer integration check.

## Final verification

| Command | Result |
| --- | --- |
| `npm --prefix frontend test -- --run` | PASS — 36 files, 192 tests |
| `npm --prefix frontend run lint` | PASS — no lint errors or warnings |
| `cd frontend && npx next build --webpack` | PASS — compilation, TypeScript, and all 14 static pages |
| `git diff --check -- frontend` | PASS |

Local command logs: `/tmp/fe-fix1-red.log`, `/tmp/fe-fix1-green.log`, `/tmp/fe-fix1-lint.log`, `/tmp/fe-fix1-build.log`.

Build emitted Node's existing `DEP0205` deprecation warning for `module.register()`; it did not fail the build.

## Verification limits

No live backend/API calls, browser screenshots, or full manual QA-P/QA-L/QA-M/QA-K passes were performed in this follow-up batch. Component interactions and timer behavior were checked with mocked APIs and hook harnesses; these do not replace real-browser layout or React lifecycle QA. Copy was compared directly with the supplied requirements and mockup source.
