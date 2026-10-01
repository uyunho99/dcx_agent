# Final whole-branch review fixes — frontend

## Scope

Implemented the four frontend findings in `final-fix1-fe.md`, using `final-review1.md` and rulings R-106 through R-110. Application/test edits are confined to `frontend/`; this explicitly requested report is the only write outside that directory. No backend files were edited by this job. No commit was made. R-107 and R-110 remain the parallel backend job’s responsibility.

## Changes

### R-108 — monitor work cannot block model export

- `components/train/trainingView.ts` excludes `kind: 'monitor'` workers from export readiness and busy/error decisions, and accepts the separate `TrainingStatus.monitor` field.
- Real train/infer failures still block model export. A running monitor continues to be polled without disabling export.
- The training page renders the secondary warning **감시를 끝내지 못했습니다**, followed by ` · ` and the reason when present. It reads the separate monitor reason, worker error/detail reason, or persisted training monitor reason, including an incomplete monitor that finishes `done`. Persisted monitor summaries without worker fields are accepted safely, and a positive incomplete count also triggers the notice.
- Tests cover every monitor worker state in both response shapes, missing/present reasons, incomplete done results, inference failure alongside monitor failure, polling, and the training page’s enabled export/secondary warning.

### R-109 — model-mode infer controls

- The labeling overview connects model-mode `infer` progress to the shared `controlLabeler` client. The endpoint is `POST /label/{sid}/judge/infer/{action}?version=...`, confirmed in the concurrently updated `backend/app/routers/labeling_v2.py`. The backend explicitly names the labeler `infer`, so the frontend uses it instead of the brief’s fallback `model`.
- `LabelerProgress` offers **일시 정지** and **중단** for running work, **이어서 진행** and **중단** for paused work, and **이어서 진행** for failed/interrupted/cancelled work. Read-only and monitor rows receive no control handler; controls are disabled while a request is pending.
- Tests cover worker-to-endpoint mapping, action availability, rendered controls/read-only behavior, and encoded infer pause/resume/stop requests.

### Known Insight — selected-version reads

- `getKnownInsights(sid, version)` now appends `?version=` through the existing URL encoder.
- Both callers—the pipeline shell’s count/list read and `KnownInsightsDrawer`—pass the selected version. The drawer effect also includes the version dependency.
- Updated API tests verify selected-version reads, encoded session/version values, and the default-version route when no version is supplied.

### R-106 — immutable prep and oneLiner after labeling starts

- The shared response parser preserves Korean backend string `detail` messages, as well as the existing structured error message. Both prep settings save and stage-0 `putContext` already use this parser and `displayError`, so both now show the backend 409 sentence verbatim:

  **라벨링을 시작한 뒤에는 이 버전에서 바꿀 수 없습니다. 새 버전에서 다시 하세요.**

- Prep reads `labeling.started` from the selected version, displays that exact sentence, and renders **규칙 수정하고 다시 실행** as a disabled button. Settings, draft save, and rerun are disabled; navigation to labeling remains available.
- Locked prep ignores stale draft rules and displays the saved rules.
- Tests verify the lock, stale draft handling, unlocked sessions, and both save clients preserving the exact 409 sentence through both response shapes.

### Verification type declaration

Standalone typechecking found two existing excess-property errors in `components/shell.test.ts`: existing UI/tests use the server-provided `activity.label`, but `SessionInfo.activity` omitted it. Added only the optional `label?: string` declaration. Existing shell tests cover the behavior; no runtime behavior changed.

## Test-first evidence

Added regression tests before implementation. The initial targeted run failed on monitor readiness/notices, missing prep lock logic, missing worker mapping helper, Known Insight version omission, and discarded 409 detail text. After the backend contract tests appeared, added the separate monitor `reason` case and updated the infer mapping expectation before adapting implementation; both new expectations failed first. Final router inspection exposed the summary-only monitor shape; its regression test also failed first and now passes. All regressions now pass.

## Verification

- `npm --prefix frontend test -- --run`: **PASS — 213 tests, 37 files**.
- `npm --prefix frontend run lint`: **PASS**.
- `cd frontend && npx tsc --noEmit`: initially found the two existing activity-label type errors noted above; corrected declaration and reran: **PASS**.
- `cd frontend && npx next build --webpack`: **PASS**, including Next.js TypeScript validation and all 14 generated pages.
- `git diff --check -- frontend`: **PASS**.
- Node emitted a non-fatal `module.register()` deprecation warning during tests/build.

## Backend integration verification

Read the updated backend code without editing it:

- `labeling_v2.py`: `labeler` accepts `jev`, `gpt`, `infer`; `action` accepts `pause`, `resume`, `stop`. Model-mode inference uses `judge/infer/{action}` and restarts failed/interrupted inference with its model ID.
- `training_v2.py`: readiness workers contain train/infer only; `monitor` is separate and can be either a worker plus result/reason or a saved result without worker fields. Both shapes are handled.
- `known.py`: `GET /known/{sid}` accepts `version` and passes it to the store.
- `prep.py` invokes the labeling-start guard on settings save; `context/store.py` defines the exact required lock sentence. The error parser preserves the backend text for both save clients.

All four frontend findings are addressed. No live provider work was started; backend runtime validation belongs to the parallel backend job.
