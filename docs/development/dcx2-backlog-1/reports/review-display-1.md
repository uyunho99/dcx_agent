### Spec Compliance

- ✅ T10 prep: `pipeline.py` clears `stage3` on both done and reused, under the session lock (`already_locked=True`). The test is parametrized over reuse.
- ✅ T10 export: `export.py` clears `stage5` only after a successful write. A failed export keeps the marker (`test_failed_export_preserves_stale`).
- ⚠️ T10 judge: `judge.py` calls `judge_done` on lease exhaustion. It clears `stage4` only when the latest run of each labeler (jev, gpt) in that version is `done`, so it matches "all judge workers done". Concern 1 below applies.
- ✅ Clearing is version-local and idempotent, and it leaves other stages alone (`test_clear_is_idempotent_and_version_local`).
- ✅ T11 rule: `StepBar.tsx:43-44` computes `max(stepIndex(currentStep), completed>0 ? completed+1 : 0)`. The +1 is correct because the stored step index is exclusive and `completedThrough` is inclusive. Highlighting, labels and navigation confirmation are unchanged.
- ✅ T11 wiring: `layout.tsx:84` passes the selected version's session, falling back to `store.sd` outside a readonly view.
- ❌ AC-08 is only partly met. The helper itself matches the spec's six milestones.

### Issues

**Important**

1. **AC-08 fails for stage 2 (crawl) in the spec's own example, "crawl done, open preprocess directly".**
   - `completedThrough` reads `session.step === 'crawl-done'` or `session.crawl.{kind,status}`. The session payload has no `crawl` key; `get_session` just returns the stored `session.json` (`sessions.py:44-52`).
   - `step` becomes `crawl-done` only inside the crawl-status handler's `sync_step` (`crawl/control.py:380-385`). That handler runs when the crawling page polls.
   - Scenario: the detail crawl finishes while no browser has the crawl page open. The user opens `/pipeline/preprocess`. Stored `step` is still `crawl-detail`, so the crawl step gets no check mark.
   - Mitigation: prep may be `done` or the step may advance on page entry. If so, stage 2 is covered by the "≥3 implies earlier" rule, which I did not verify. A step-3 viewer who has not run prep is the uncovered case.
   - Fix: have the server include crawl completion in the session payload, or derive it from `collectionId` plus run status. Alternatively, record the gap in the decision log.

2. **Stage 4 never lights up from `labeling.status === 'done'`.**
   - Nothing in the backend writes `labeling.status = 'done'`. Only `versions.py:145` writes `'stale'`.
   - `judgeRuns` holds run IDs, not states. The helper's stage-4 branch is therefore dead code against real payloads.
   - Scenario: labeling finishes, the user opens the training page directly, and the labeling step is not checked unless `step` advanced.
   - The T11 report admits this but still treats it as follow-up. Both T10's `judge_done` and `export.write` already hold the lock where this status could be set. A one-line `labeling.status='done'` write at the same point as `clear_stale('stage4')` would fix it.

3. **Stage 6 has the same gap.** `session.clusters` is not in the payload; cluster results live in `/cluster-status/{sid}`. That branch is also dead code, which matches the T11 report.

Only the prep (3), `exportRef` (5) and keyword (1) milestones work from real session data, plus step 2 when `step` was synced.

**Minor**

4. `judge_done` is a stage-clearing helper that also writes run state. It marks the run `done` itself, ahead of the generic worker's own publish. That works, because the worker's final UPDATE only touches active runs, but it duplicates state-transition logic. Review the interaction with a late `stop` or `pause` once, as the T10 report notes.

5. If one labeler has a permanently failed or `bad` document and still exhausts its leases, it counts as `done`. Stage 4 stale is then cleared even though some documents have no vote. This is probably acceptable, since "exhausted" is the existing definition of done.

6. `export.py` places the new import inside an existing import group, with a stray blank line above it. This is cosmetic.

### Assessment

T10 is functionally sound. The AC-07 stale clearing is correct, locked, and covered by tests. T11's helper and StepBar logic are correct, but only half of the intended signals reach it. The common case from the spec (crawl done, preprocess opened directly) depends on `step` having been synced, and stages 4 and 6 never trigger. AC-08 is not fully met, and the unit tests pass only because they feed synthetic session shapes. To fix it, the backend needs to expose or write completion signals for crawl, labeling and clusters. Alternatively, `layout.tsx` could pass the status data it already fetches.

Task quality: Needs fixes
