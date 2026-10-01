**Verdict: Approved.** All 15 items are addressed and I found no Critical or Important issues. Four Minor issues can wait. This was a read-only review of the diff and current sources at 35bc291. I re-ran no tests and relied on your 35bc291 results.

**Backend**

| # | Verdict | Where / notes |
|---|---|---|
| 1 R-106 | Addressed | `context/store.py:21-26` has the exact message and returns 409 using `StoreError`'s defaults. Context: `routers/context.py:47-58`, which only locks when oneLiner actually changes, plus the new PATCH at `:103`. Prep: `routers/prep.py:81`, where the lock is checked before the running check. Training: `train.py:55` reads `votes_json['jev']`, and agreed rows always store both votes (`route.py:110`). **Stage 0-2 is not broken:** `labeling.started` is only set at labeling start (`labeling_v2.py:91,99`), and saving the same oneLiner still passes. **New version then edit works:** restarting at stage ≤4 resets `started=False` (`versions.py:123-128`), and `test_final_fix1.py:45-46` covers it. A version restarted from stage 5 or 6 stays locked, which matches the ruling. |
| 2 R-107 | Addressed | `known/store.py:49-69`. Non-stage0 dict records are kept as they are. Unchanged stage-0 text reuses the existing record, so `id` and `vectorRow` are preserved. Only new or changed text goes to `_embed_many` in one batch. Legacy string items are treated as stage-0 and matched. |
| 3 R-108 | Addressed | `monitor.py:101-105` catches per-sample errors, releases leases, records `errors`, and finishes with `state='done'` plus a reason. `training_v2.py:59-70`: `workers` now holds only train/infer, and the monitor is reported separately. Export (`export.py:14`) does not gate on the monitor. |
| 4 R-109 | Addressed | `labeling_v2.py:108-128` accepts `infer` with pause/resume/stop and rejects a labeler that doesn't match the current mode. Resume restarts a failed or interrupted run as kind `infer` and updates both run references. Stop ends a run as `interrupted` (`worker.py:35`), so resuming after stop restarts it. |
| 5 R-110 | Addressed | `votes.py:53-73`. **It cannot steal from a live active run:** a live owner keeps its lease if its PID matches `runs.pid`, its state is running/paused, its heartbeat is under 60 s old (the heartbeat thread writes every 10 s), and the lease is under 600 s old. `runs.sqlite` is per session and covers every version, and the cache path's first segment is the session id (`judge.py:39`), so an owner from another version isn't wrongly treated as inactive. A displaced owner's `put`/`fail` calls are blocked by `run_id IS ?`. The wait loop is bounded (`judge.py:133-140`) and ends the run as `interrupted`, never `done`. `monitor._claim` uses the same `reclaim`. |
| 6 | Addressed | `worker.py:103-107` |
| 7 | Addressed | The duplicate is removed and no imports remain; `route.py:69` imports only `merge`. |
| 8 | Addressed | `train.py:127,253` |
| 9 | Addressed | `routers/known.py:31`, `known/store.py:44-46` |
| 10 | Addressed | `prep.py:63` |
| 11 | Addressed | `route.py:236` |

**Frontend**

| # | Verdict | Where / notes |
|---|---|---|
| 1 R-108 | Addressed | `trainingView.ts` `trainingState` leaves monitor workers out of the readiness check and builds the notice. It handles both shapes: the separate `monitor` field and a `kind: 'monitor'` worker. Page banner: `training/page.tsx:95`. |
| 2 R-109 | Addressed | `workerControls.ts` `controlTarget` returns `'infer'` in model mode. It is wired into `Overview.tsx:54` and calls `POST /label/{sid}/judge/infer/{action}?version=`, which is exactly what the backend accepts. The monitor row gets no controls. |
| 3 | Addressed | `api/known.ts` adds `?version=`. Callers pass it: `pipeline/layout.tsx:49` and `KnownInsightsDrawer.tsx:18`. The backend accepts it. |
| 4 R-106 | Addressed | `errors.ts` keeps the backend message, so both prep save and stage-0 save show the 409 sentence word for word. `prep.ts` `prepEditLock` plus `PrepScreen.tsx:56,140,151` show the sentence and render "규칙 수정하고 다시 실행" as a disabled button. |

**Backend and frontend agree (they were written in parallel):** the frontend's `TrainingStatus.monitor` type (`Partial<Worker> & {incomplete}`) matches the backend's merged dict of the saved result plus the run row plus `reason`, or the saved result alone, or null. The `?version=` param lines up for the known-insights read and for control calls.

**New issues**

*Critical:* none.

*Important:* none.

*Minor:*
1. **Monitor reason is dropped when the run finishes `done` with errors.** `training_v2.py:64-68` builds `{**saved, **monitor_run, 'reason': reason}`, and `reason` comes out null, which overwrites the saved reason ("감시 표본 N건을 완료하지 못했습니다."). The frontend still shows the right notice because it falls back to `training.monitor.reason`, but the API field is wrong.
2. **A failed monitor's reason can be a bare exception class name.** It falls back to `monitor_run.error`, so the page could show "감시를 끝내지 못했습니다 · ValueError". The fixed fallback text (`:66-67`) only applies when there is no error value.
3. **A lease's `at` timestamp is never refreshed during a batch.** A live owner whose Jev or GPT batch runs past 600 s could lose the rest of that batch to a worker in another version. The displaced writes are blocked, so the cost is duplicate provider calls, not wrong data. This follows the brief and R-110 as written. Refreshing `at` on heartbeat would close it.
4. **Stage-0 saves now call the embedder synchronously while holding the session lock** (`replace_stage0` → `_embed_many`). This was requested. But before prep has run, it embeds with the default backend, not the embedder prep will later choose. That is the same existing behaviour as adding from the drawer, and it only matters if prep picks a different embedder than the default.

The three deferred concerns (paused-worker polling on a read-only version, manual audit using a schedule slot, a running monitor blocking version creation) were left out as planned.

**Verdict: Approved**
