# Final whole-branch backend fix report

## Scope and requirements

Implemented all 11 backend items from `.superpowers/sdd/03-plan/final-fix1.md`, using the scenarios in `final-review1.md` and rulings R-106 through R-110 in `docs/development/dcx2-stage3-5/decision-log.md`.

Edits are confined to `backend/` and this report. No commits or package installations were performed. The pre-existing decision-log modification and the parallel job's frontend changes were not edited.

## TDD evidence

Before changing application code, added `backend/tests/test_final_fix1.py` with a regression for every item, including parameterized failure scenarios.

- **RED command:** `backend/.venv/bin/python -m pytest backend/tests/test_final_fix1.py -q`
- **RED result:** **30 failed**, 1 warning, 3.83 seconds. All failures were the intended missing behavior: wrong HTTP status, lost records, stale training cache lookup, failed monitor run, unavailable infer control, unreclaimed lease/unbounded wait, incorrect worker state, duplicate materializer, ignored setting, wrong version, stale status, or retained automatic confidence.
- **Initial GREEN command:** same command.
- **Initial GREEN result:** **30 passed**, 1 warning, 3.64 seconds.
- Strengthened the monitor tests to raise errors at the actual Jev/GPT provider boundaries and verify lease release and successful export. Strengthened the bounded-wait test to assert durable `interrupted` status. Added two positive controls proving fresh running/paused owners retain their leases.
- **Final focused GREEN:** **32 passed**, 1 warning, 3.90 seconds.

All test names below are in `backend/tests/test_final_fix1.py` unless another file is named explicitly.

## 1. R-106: lock earlier-stage changes; train from stored votes

**RED:** `test_r106_context_lock[put/patch]`, `test_r106_prep_lock`, and `test_r106_targets_use_final_votes_without_cache` failed. PUT context/prep allowed changes, PATCH context was unavailable, and missing current-cache probabilities raised `KeyError`.

**GREEN:** All four cases pass. Once `labeling.started` is true, prep configuration writes and oneLiner changes return HTTP 409 using the existing error envelope and the exact message:

> 라벨링을 시작한 뒤에는 이 버전에서 바꿀 수 없습니다. 새 버전에서 다시 하세요.

Both context methods serialize validation and mutation under the session lock. Other context fields remain editable; creating a version restarted from stage 3 permits a new oneLiner. Rejected writes leave the session unchanged. Added partial PATCH context support using the same save path. Training binary and Non-reason soft targets read the final row's `votes_json['jev']`, alongside its stored GPT vote, regardless of an empty or conflicting current cache.

**Files:** `backend/app/context/store.py`, `backend/app/routers/context.py`, `backend/app/routers/prep.py`, `backend/app/model/train.py`, `backend/app/routers/training_v2.py`, `backend/tests/test_final_fix1.py`. Existing synthetic final-row fixtures in `backend/tests/model/test_train.py` and `backend/tests/model/test_model_mode.py` now include both stored votes, as production final rows do.

## 2. R-107: preserve other Known Insight sources

**RED:** `test_r107_preserves_known_and_embeds_only_changed` demonstrated that context saving deleted drawer/rag/prev_session items and discarded the unchanged stage-0 vector pointer.

**GREEN:** The test passes with reordered, edited, added, and removed stage-0 statements. Only stage-0 items are replaced. Unchanged text retains its ID and vector pointer, other-source records survive unchanged, and only new/changed text is embedded in a single `_embed_many` batch. Repeating the save makes no embedding call. IDs remain unique.

**Files:** `backend/app/routers/context.py`, `backend/app/known/store.py`, `backend/tests/test_final_fix1.py`.

## 3. R-108: monitor errors do not block export readiness

**RED:** Four `test_r108_monitor_records_sample_errors_and_finishes` variants (`jev`, `gpt`, `store`, `transport`) ended as failed runs. `test_r108_failed_monitor_is_separate_from_readiness` found the failed monitor in `workers`.

**GREEN:** All five cases pass. Per-sample JevError, LabelerPaused, StoreError, HTTP transport errors, and OSError are caught; the document ID and safe exception-type reason are recorded in `training.monitor.errors`. Leases are released, later samples continue, and the run completes `done` with incomplete counts and a reason. Provider exception messages are not exposed. Tests verify that model export succeeds despite an incomplete sample.

Training status reports the monitor separately under `monitor`, including state and reason, and limits readiness `workers` to train/infer. A monitor that fails outside sample handling is still visible without blocking readiness.

**Files:** `backend/app/model/monitor.py`, `backend/app/routers/training_v2.py`, `backend/tests/test_final_fix1.py`.

## 4. R-109: infer pause/stop/resume

**RED:** Five `test_r109_infer_controls_and_idempotent_restart` cases returned validation errors for `/label/{sid}/judge/infer/{action}`.

**GREEN:** Pause and stop reach the active inference run, and resume reaches a paused run. Resuming failed/interrupted inference starts kind `infer` with the selected model and updates both labeling and training run references. Repeating resume controls the replacement run without another launch. The session lock and existing runner deduplication serialize restarts; LLM judge control remains available in LLM mode.

**Files:** `backend/app/routers/labeling_v2.py`, `backend/tests/test_final_fix1.py`.

## 5. R-110: reclaim stale leases and bound judge waiting

**RED:** Six `test_r110_reclaims_alive_pid_leases` cases failed for an inactive run, a missing run, and a lease older than 600 seconds, each through judge leasing and monitor claiming. The owner's PID remained alive. `test_r110_judge_wait_is_bounded` hit its watchdog because the wait loop never terminated.

**GREEN:** All seven regressions pass, plus two fresh-owner controls. Shared reclamation checks the session's `runs.sqlite` read-only, PID identity/liveness, active run state/heartbeat, and lease timestamp. Expired pending leases are released after 600 seconds. Both claim paths use this helper inside their vote transaction. Writes from a displaced owner cannot complete the newly leased row. Standalone caches without a session registry retain PID/age checks.

The judge permits at most 6,000 consecutive empty lease polls (0.1-second sleeps), attempting safe reclamation on every poll. If ownership still prevents progress, it records a reason and marks the run `interrupted` for resume. It does not steal fresh active leases or mark unfinished judging done. Running and paused owners with fresh leases are protected by explicit tests.

**Files:** `backend/app/label/votes.py`, `backend/app/label/judge.py`, `backend/app/model/monitor.py`, `backend/tests/test_final_fix1.py`.

## 6. Worker BaseException handling

**RED:** Both variants of `test_minor6_base_exception_is_interrupted_and_reraised` showed SystemExit/KeyboardInterrupt propagating while the durable run incorrectly became `done`.

**GREEN:** Both pass. `execute` catches BaseException, records non-Exception exits as `interrupted` with the exception type, then re-raises after the final status write. Ordinary Exception failures keep the existing `failed` behavior.

**Files:** `backend/app/work/worker.py`, `backend/tests/test_final_fix1.py`.

## 7. Remove duplicate final materializer

**RED:** `test_minor7_single_final_materializer` found `merge.rebuild_final` still present.

**GREEN:** The duplicate is deleted. Production callers already used `route.rebuild_final`; no production import needed replacement. Existing merge/audit/route tests were migrated to the active implementation. Tests that previously exercised combined final/queue materialization now invoke route final rebuilding and queue reconciliation, retaining their existing behavioral assertions.

**Files:** `backend/app/label/merge.py`, `backend/tests/label/test_merge.py`, `backend/tests/label/test_audit.py`, `backend/tests/label/test_route.py`, `backend/tests/test_final_fix1.py`.

## 8. Honor head_min_samples

**RED:** `test_minor8_configurable_head_minimum[train_member/train_ensemble]` trained heads despite `settings.head_min_samples=1000` on a 40-row corpus.

**GREEN:** Both pass. Standalone member training and ensemble head eligibility use the setting. Insufficient heads remain untrained, with zeroed head weights and the existing metrics reason.

**Files:** `backend/app/model/train.py`, `backend/tests/test_final_fix1.py`.

## 9. Version-aware Known Insight reads

**RED:** `test_minor9_known_reads_past_version` returned active-version items for `?version=v1`.

**GREEN:** The endpoint and store accept an optional version and read that version's session data. The test verifies old-version items, unchanged old-version session bytes, and HTTP 404 for a missing version.

**Files:** `backend/app/routers/known.py`, `backend/app/known/store.py`, `backend/tests/test_final_fix1.py`.

## 10. Preserve stale prep status

**RED:** `test_minor10_stale_prep_wins_over_completed_run` returned `done` when the prep state was stale but retained an old completed run ID.

**GREEN:** The test passes. `_view` preserves the explicit stale state instead of overriding it from the old worker, and GET status leaves the persisted state stale.

**Files:** `backend/app/routers/prep.py`, `backend/tests/test_final_fix1.py`.

## 11. Human escalation confidence and mismatch

**RED:** `test_minor11_human_clears_automatic_mismatch` retained automatic confidence 0.2 after human escalation.

**GREEN:** The test passes. The conflict-update path now sets human confidence to 1 and clears `grade_mismatch` to 0, matching the human insert path while preserving vote history.

**Files:** `backend/app/label/route.py`, `backend/tests/test_final_fix1.py`.

## Full validation

- Required full-suite command: `backend/.venv/bin/python -m pytest backend/tests -q`.
- Full-suite result: **1,214 passed**, 2 warnings, 119.81 seconds. This run collected the original 30 regressions before the two additional positive controls were added; the final focused run independently passed all 32 tests after the strengthened checks.
- Warnings: existing Pydantic class-based configuration deprecation and joblib physical-core detection fallback; neither caused a test failure.
- Final focused suite: **32 passed**, including all 30 original RED cases and two fresh-lease positive controls.
- `git diff --check -- backend`: clean.
- No frontend validation was run by this backend job.

The three explicitly parked concerns remain outside this fix: read-only-version paused worker polling, manual audit schedule slots, and running monitors blocking version creation.
