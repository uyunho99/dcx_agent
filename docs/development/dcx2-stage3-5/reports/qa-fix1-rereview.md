**Re-review Q1–Q12: all changes are in place except two unresolved details (Q8 root cause, Q12 nameless button), and no new issues block approval.** I read the diff and the changed files only. I ran no tests and no browser; the reports and the controller supply the test results.

## Per-finding verdicts

| Q | Verdict | Evidence |
|---|---|---|
| Q1 | Addressed | Backend `routers/prep.py` `_view` returns `config` from `PrepConfig.model_validate(prep.get('config', {}))`, which defaults to `settings.embed_backend`. Frontend `prep.ts:34` `prepConfig(..., serverConfig)` uses it, and `PrepScreen` passes `current.config`. Saved and draft values still take precedence. |
| Q2 | Addressed | `chat.py` `_unconnected` returns `status:'ok'`, the found `sources`, and `reason` when a `sid` was sent. The message is exactly `답변 모델이 연결되지 않아 근거 원문만 보여 줍니다.` `ChatPanel.tsx:10` throws only on `status==='error'`, so the ok reply now renders the source cards. Details are in the compatibility section below. |
| Q3 | Addressed | `PrepScreen` header adds `<RestartVersion stage="stage3" label="3단계부터 다시">`. `versions.py:244` already supports stage3 restarts. The drawer popover gets a new `contained` mode (`Popover.tsx`, `ds.css` `.ds-pop-contained`, `VersionPicker.tsx`). Not checked in a browser. |
| Q4 | Addressed | Backend `labeling_v2.py` exposes `progress.infer` and `progress.monitor` with `done`, `total`, `pending`, `bad`, `estimate`, `reason`, fed by `detail.done`/`detail.total` from the worker heartbeats. The frontend `LabelProgress.total?` and `LabelerProgress.tsx` read those same names, and Jev/GPT cards without `total` keep the old path. |
| Q5 | Addressed | Backend adds `embedder_name()`, which returns `fake` or the model name, and applies it to `manifest.embedderName`, `stage3.embedder`, `training.embedderName` and registry `embedderName`. Frontend `embedderLabel()` shows `가짜 임베더` or `voyage-4 · 1024`. The field names agree across `PrepResult`, `TrainingResult` and `ModelRepository`. |
| Q6 | Addressed | Backend `reused` is persisted and true only when a finished manifest was reused (`pipeline.py`, `prep.py`); config edits and new runs reset it. Frontend `PrepResult.tsx` shows the banner only when `status.reused === true`. |
| Q7 | Addressed | `KnownInsightsDrawer.tsx` is now `inset:0 0 0 auto`, width 360, height 100dvh. The label and textarea use `ds-field`, `ds-lab` and `ds-inp`. Not checked in a browser. |
| Q8 | Partially | Frontend: `StepBar` highlights the viewed route via `usePathname`. Backend: it says the "학습 중" badge could not be reproduced. `store.py:150-186` already excludes finished latest runs, and four regression tests were added. The original observation stays unexplained, so this is unverified rather than fixed. |
| Q9 | Addressed | `LabelerProgress.tsx`: `waiting` covers none, pending and idle; it shows `대기 중` with a zero bar. Backend `overview.py:162` emits `none` before a run exists. |
| Q10 | Addressed | `restartLabelNotice` (`browserQa.ts:11-13`) uses the exact 9.1 text, and `versions.py:129` confirms the same string. It uses the real `parentVersion` and shows only when `restartFrom==='stage4'`. |
| Q11 | Addressed | `overview.py:138,170`: `mismatchRate = count(queue where reason='grade_mismatch', any status) / merged`. |
| Q12 | Partially | Done: the select has `aria-label="내부용 · 임베더"`, and Known Insight gets an `aria-label` plus a `pipeline-foot-label` class that the collapsed sidebar hides (`globals.css:46`). Not done: the nameless sidebar button is never identified, and the frontend report's "already exposes accessible names" is an assertion. The shared `Tabs` already has `role=tab`, so no tab change was made and none was verified. |

## Q2 compatibility with stage 0-2 callers

- `ChatRequest` and `InsightChatRequest` default `sid` to `"s0"`. `_unconnected` treats a request without an explicit `sid` as legacy: status `error`, empty sources, and only the message changed.
- The stage 0-2 `insights/layout.tsx` `handleChat` reads only `d.answer`. It works under either status and now shows the new message.
- The existing pipeline callers that send a `sid` now get the ok reply with sources.

## New issues

**Critical:** none.

**Important:** none.

**Minor:**
1. `StaleBanner` (`StageVersion.tsx:45-46`) returns the restart notice first, so it hides the stale-stage warning on stage 4. It also shows on every stage-4 view of a restarted version, with no dismissal.
2. Q12 is only partially evidenced: the nameless button is unidentified, and the tab claim rests on the report.
3. Q11 counts every `grade_mismatch` queue row. I did not check whether a document can have more than one such row, which would inflate the rate above the per-document count the brief specifies.
4. The frontend has no live browser re-QA. Q3, Q7 and Q12 need a visual check during the combined re-QA. The report says Chrome was unavailable.
5. `embedderLabel` falls back to a hardcoded `1024` dimension when only a string name is passed. That is harmless today.

Verdict: Approved
