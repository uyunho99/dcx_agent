### Strengths
- **Shared worker runner.** `work/runner.py`, `worker.py` and `status.py` launch and deduplicate a run inside one `BEGIN IMMEDIATE` block, keyed by (version, kind, labeler). The heartbeat keeps running while a worker is paused. Crawl and codex now share one `pid_alive`, so stage 0-2 are unaffected.
- **Vote caches.** The caches live outside the version. They have append-only journals (`route_vote_changes`) and a cursor per version (`route_sync`), so two workers syncing at once cannot lose a paired vote.
- **Version copy.** It uses the SQLite backup API, skips `-wal`/`-shm` files, and `_restart_labels` resets the label tables while keeping `human`, as the design requires (line 116).
- **Stage-5 output.** `write_stage5` is the only writer, and export refuses while any queue item is open.
- **Queue reasons match the spec.** LLM mode uses only `labeler_failed` and `grade_mismatch`. Model mode uses `model_uncertain` and `model_disagree` (design line 344).
- **Audit.** The schedule is 1,000, then every 10,000, with a fixed seed and reservoir sampling. There is no τ, α or boundary code left. Model-side temperature scaling only is fine.
- **Search.** Pinecone is fully removed. Search is local float16 cosine, limited to the relevant set, with a persona fallback when there are no vectors or labels.

### Issues

#### Critical
None.

#### Important
1. **Changing an earlier stage in the same version never updates labels.**
   - `route.rebuild_final` clears results only when the rule or question version changes (`route.py:87-95`). It merges only documents that have no `final` row yet (`route.py:96-100`).
   - The caches follow the current oneLiner and prepKey (`overview.py:34-39`).
   - *Scenario A:* the user edits oneLiner in stage 0 after labeling. `PUT /context` allows this with only a warning. The resumed judge says "판정 맥락이 바뀌어 다시 판정합니다" (`judge.py:94,106`) and pays for Jev/GPT calls, but `final` keeps the old-context labels. Training then crashes with `KeyError` (`train.py:61,67`, deferred T12), because the new Jev cache is empty.
   - *Scenario B:* the user uses "규칙 수정하고 다시 실행" after labeling started. `prep.py:85` resets `derivedRef` while `labeling.started` stays true. Export fails with "모든 문서의 판정…". There is no way to re-judge in the UI: the start button is hidden, and resume only works on failed or interrupted runs (`labeling_v2.py:118`).
   - *Fix:* once labeling has started, return 409 "새 버전에서…" for prep config changes and oneLiner changes, like the D-139 mode lock. Or add prep/context identity to the invalidation check.
2. **Saving stage 0 wipes Known Insights.** `context_patch` (`routers/context.py:49-51`) rewrites `knownInsights` as the stage-0 strings only.
   - *Scenario:* at stage 7 the user adds drawer statements and "근거 원문" items. They then go back and fix the research question. All drawer, rag and prev_session items are deleted. Stage-0 items lose `vectorRow` and are not re-embedded. The "새 발견" filter then excludes nothing, and every item shows the warning.
   - *Fix:* replace only the `origin=='stage0'` items, and re-embed any that changed.
3. **In model mode, a monitor failure blocks export with the model.**
   - `monitor.run_worker` has no handling for `JevError`, `LabelerPaused` or `StoreError` (`monitor.py:80-99`), so any provider error marks the run failed.
   - The training status includes `monitorRunId` (`training_v2.py:59-61`).
   - `trainingState` treats any failed worker as not ready (`trainingView.ts:15-17`).
   - *Scenario:* no Jev key, or one 5xx during the 1% sample. "학습 결과로 내보내기" is disabled, and only export without the model remains.
   - *Fix:* catch errors per sample, record the item as incomplete, and finish `done` with a reason. Or leave the monitor out of readiness.
4. **An interrupted model-mode inference cannot be resumed.**
   - The labeling overview wires pause/resume controls only for jev and gpt, and the backend's judge control endpoint returns 409 in model mode (`labeling_v2.py:112-113`). The start button is hidden after start.
   - *Scenario:* the user stops inference, it crashes, or the heartbeat goes stale for more than 60 s (`status.py:47-50`). Stage 4 is stuck on "이어서 진행" with no button to press.
5. **A vote lease is freed only when its owner PID is dead** (`votes.py:48-51`, deferred T08). Combined with the judge's wait loop, which has no time limit (`judge.py:128-132`), this can hang a run.
   - *Scenario:* the Mac mini reboots mid-run and a leased owner's PID is reused. The resumed run finishes everything except that batch of 20-50 documents. It then waits in a 0.1 s loop forever at 99.x% and never reaches "done". `monitor._claim` raises `StoreError` on the same rows.
   - *Fix:* also reclaim when the owner's run is no longer active in `runs.sqlite`, or when `at` is older than N minutes.

#### Minor
- `worker.execute` catches only `Exception`. A `SystemExit` or `KeyboardInterrupt` is recorded as `done`. A judge marked `done` with documents still pending gets no resume button. Catching `BaseException` is a one-line fix.
- The spec allows creating a new version while a judge is paused (design 399). That worker keeps running when its version becomes read-only. It polls `runs.sqlite` with `BEGIN IMMEDIATE` every 100 ms, forever, and the UI cannot stop it because control requires a writable version.
- A manual audit uses up a slot in the automatic schedule (`labeling_v2.py:196`). A manual round at 300 accepted pushes the next automatic round to 11,000 instead of 1,000. The accepted count also shrinks as audits move rows to `audited` (`audit.py:141`).
- `merge.rebuild_final` (`merge.py:38-92`) is a dead duplicate with different behavior: it does not exclude model rows and inserts while iterating a live cursor (deferred T09). Delete it.
- The `head_min_samples` setting is unused; `train.py:133,259` hard-code 30.
- `getKnownInsights` ignores `version` (`known.ts:5`) while add, edit and delete pass it. The drawer on a past version shows the active version's items.
- After "3단계부터 다시", the `stale` prep status is overwritten by the old run's `done` state, because `_view` looks the run up by the kept `runId` (`prep.py:60-64`).
- A running monitor ("감시 중") blocks creating a new version, but the spec lists only prep, judge, train and infer.
- A human escalation leaves `grade_mismatch=1` and the old confidence on the human row (`route.py:233-239`).

### Deferred minors that must be fixed
- **T12** (`votes_json['jev']` instead of a cache lookup): it causes the training crash in Important 1.
- **T13** (monitor aborts on a provider exception): this is Important 3.
- **T08** (PID reuse blocks lease reclaim): this is Important 5.
- **T01** (`BaseException` recorded as `done`): cheap, and it can leave a run impossible to resume.

The other deferred minors are not load-bearing together.

### Declined to judge
- Overview polling cost at 300k documents (full-table scans every 5 s): I noted it but did not measure it.
- Legacy sessions losing chat retrieval: an intended result of removing Pinecone.
- UI copy and wording.
- Codex-sandbox constraints, which you said are irrelevant.

### Assessment
**Ready to merge? With fixes.**

**Reasoning:** The storage, runner and version layers are sound. Five integration gaps can silently produce stale or lost results (1, 2) or leave a stage stuck with no recovery in the UI (3, 4, 5). Each fix is local: a guard, a merge rule, error handling, or a lease-expiry condition.
