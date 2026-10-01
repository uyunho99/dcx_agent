# DCX2 stage 3–5 browser QA frontend fix report

Date: 2026-09-30

## Scope and outcome

Implemented the frontend dispatch in `.superpowers/sdd/03-plan/qa-fix1-fe.md`, using the QA report, supplied Q3/Q7 screenshots, R-112, and design sections 6.3/9.1. Application changes are confined to `frontend/`. This requested report is the only file written outside that directory. No backend files were edited by this job, and no commit was created. Backend changes visible in the shared worktree belong to the parallel job.

All required automated checks pass. Live browser re-QA remains unverified: the computer-use tool could not open Chrome (`Browser is not available: chrome`), and its browser inventory returned an empty list. No new browser screenshots or end-to-end visual pass are claimed.

## Findings addressed

| Finding | Frontend result |
| --- | --- |
| Q1 | Prep initial loading consumes the resolved `config` from `/prep/{sid}/status`, including `embedder`, `embedModel`, and `embedDim`. Saved choices and eligible drafts retain precedence; existing crawl rule inheritance is preserved. The first form now follows server `EMBED_BACKEND` with the updated backend. |
| Q2 | Existing `ChatPanel` normalization/rendering already accepts successful replies regardless of answer wording and retains sources/reason. Strengthened the chat flow regression to use status `ok` and the exact answer `답변 모델이 연결되지 않아 근거 원문만 보여 줍니다.`; it verifies the answer, source-card props, Known Insight addition callback, subsequent filtered search, and switch-off search. No unnecessary chat production rewrite. Existing source-card/API code performs the document addition. |
| Q3 | Added `3단계부터 다시` to the prep page header using `RestartVersion` with `stage3`. Added a contained Popover mode for the version drawer's `이 버전에서 새로 시작하기`: the form flows within the drawer width and scroll area instead of extending left from the trigger. |
| Q4 | `LabelProgress` accepts backend `total`. Shared worker cards render actual done/total and remaining counts for infer and monitor; existing worker controls remain intact. |
| Q5 | Shared embedder formatting displays `fake` as `가짜 임베더` and Voyage as `voyage-4 · 1024`. Prep result metadata and its setup summary, training result, and model repository consume actual identities. Model views prefer backend `embedderName`, with structured `embedder` fallback. Missing metadata displays `확인 불가`. |
| Q6 | Removed the frontend inference that a completed result with no run ID must be reused. The banner now requires `reused === true`, matching the updated backend flag. |
| Q7 | Known Insight is a right-edge, full-height 360px modal drawer (viewport-width cap for narrow screens). The `새 문장` label and textarea use the existing grid field/input styles, separating the label and input. Existing focus restoration, Escape dismissal, and panel shortcut exclusion remain. |
| Q8 | StepBar gets its current highlight and `aria-current` from the viewed route. Done checks still derive from stored session progress. Completion/activity payload correction belongs to the backend job; existing frontend activity polling consumes that payload. |
| Q9 | Idle/none/pending workers display `대기 중` and a zero-valued progress bar rather than an indeterminate `처리 중…` caption. |
| Q10 | Stage-four restart banner uses actual `parentVersion` and exact text: `이 라벨은 v1 기준입니다. LLM 판정은 재사용하고 사람 검수만 다시 합니다.` (substituting the real parent, tested with v7). It is limited to stage-four restart lineage on the labeling stage. |
| Q11 | Mismatch numerator/denominator correction belongs to the backend job. Frontend continues displaying server `mismatchRate` without recalculating it from the open queue. |
| Q12 | Embedder select explicitly exposes `내부용 · 임베더`. Known Insight trigger has an accessible name/count and tooltip; its visible label uses the existing collapsed-sidebar hiding rule, leaving its icon instead of clipped `Know` text. Version/API sidebar controls already expose accessible names. Labeling already uses the shared semantic Tabs component; added regression coverage for tablist, three tabs, one selected tab, and linked panels. |

## Backend contracts checked in the shared worktree

- `backend/app/routers/prep.py`: status returns resolved `config` and explicit `reused`.
- `backend/app/prep/pipeline.py` and `backend/app/vectors/embedder.py`: stage-three `embedder` is the real display identity (`fake` or model name).
- `backend/app/routers/labeling_v2.py`: `progress.infer` and `progress.monitor` expose top-level `done`, `total`, `pending`, plus worker progress/state.
- `backend/app/model/registry.py`: model responses expose `embedderName`; structured embedder metadata remains available.
- `backend/app/routers/training_v2.py`: training metadata preserves embedder identity.
- Chat success contract retains answer, sources, reason, and status for the no-answer-model path.

These contracts were read only. Backend tests were not run or claimed by this frontend job.

## Tests and verification

Vitest-first sequence:

1. Added route/worker/embedder/restart regressions before implementation; first run failed because the new formatting/notice module did not exist. The strengthened no-LLM chat regression passed against existing behavior.
2. Added prep server-default regression; observed the expected failure (`voyage` instead of `fake`), then wired server configuration into prep loading.
3. Added reuse-banner regression; observed the erroneous banner for `reused: false` with no run ID, then removed the inference.
4. Added semantic tab rendering coverage and ran the complete suite.

Final checks after the last code changes:

- `npm --prefix frontend test -- --run`: **PASS — 41 files, 230 tests**.
- `npm --prefix frontend run lint`: **PASS — zero errors/warnings**.
- `cd frontend && npx next build --webpack`: **PASS — compilation, TypeScript, and all 14 static pages generated**.
- `git diff --check -- frontend`: **PASS**.

An intermediate lint/build attempt found an import placed before `use client` in ModelRepository. The directive ordering was corrected and the final checks above passed. Node emits an environment-level `module.register()` deprecation notice during tests/build; it does not fail either command.

New regression files/helpers: `frontend/src/components/browserQa.test.ts`, `frontend/src/lib/logic/browserQa.ts`. Existing chat and prep tests were extended. Production edits cover the shell/StepBar, shared Popover, Known Insight drawer, worker progress, prep screen/settings/result, training result/repository, version restart/banner/drawer, and wire types.

## Remaining browser verification

Re-run the supplied QA scenarios against the combined backend/frontend changes, especially:

- no-key chat answer + source cards + actual Known Insight addition;
- stage-three restart and contained version-drawer form;
- 360px full-height drawer/input spacing at 1440×900 and 1024×768;
- actual infer/monitor counts and fake-embedder labels;
- stage-four parent banner, route current marker, idle workers, and collapsed-sidebar accessible controls.

This report establishes automated frontend verification, not completion of the separate combined browser-QA rerun.
