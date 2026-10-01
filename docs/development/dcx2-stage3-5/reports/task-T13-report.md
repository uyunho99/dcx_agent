# T13 implementation report

Date: 2026-09-30. Workspace: `/Users/persona1/Desktop/dcx_agent-dcx2-stage3-5`.
Branch verified: `feature/dcx2-stage3-5`. No network access, git write commands, or commits were used.

## Scope and outcome

Implemented the backend model registry, reusable ensemble inference, stage-five exports, classifier-mode labeling, monitoring, and training APIs. Read `task-T13-brief.md`, design r2 sections 5.2–5.7, 8, and 9, and the actual T01/T02/T08/T09/T11/T12 interfaces. Controller rulings take precedence over the design's obsolete distillation wording. No distillation file or endpoint exists; saved `kind` is always `ensemble`.

The legacy removal is a separate logical change confined to `backend/app/services/training.py`: both TensorFlow and sklearn three-model training/classification implementations were removed. The existing legacy router remains intact; its background service now only reads saved legacy `training` or `stage_5.json` results into the existing job-status projection. Versioned sessions receive a read-only error from that old service. No old session or classification artifact is written by this path.

## Exact application files

Created:

- `backend/app/model/registry.py`
- `backend/app/model/infer.py`
- `backend/app/model/export.py`
- `backend/app/model/monitor.py`
- `backend/app/routers/training_v2.py`

Modified:

- `backend/app/main.py`
- `backend/app/work/worker.py`
- `backend/app/services/training.py`
- `backend/app/label/route.py` — permitted integration hook, detailed below.
- `backend/app/routers/labeling_v2.py` — permitted model-mode integration hook, detailed below.

Created tests:

- `backend/tests/model/test_registry.py`
- `backend/tests/model/test_infer.py`
- `backend/tests/model/test_export.py`
- `backend/tests/model/test_model_mode.py`

Report and command evidence are under `.superpowers/sdd/03-plan/` (this directory is ignored by the repository):

- `task-T13-report.md`
- `task-T13-red.log`
- `task-T13-red-integration.log`
- `task-T13-red-overview.log`
- `task-T13-red-audit.log`
- `task-T13-green.log`
- `task-T13-refactor-tests.log`
- `task-T13-full-tests.log`
- `task-T13-model-tests.log`

## Implementation details

### Registry and training

`save(result, meta)` writes `members/m0.pt` through `members/m3.pt`, `calib.json`, and `meta.json` into a hidden staging directory, then publishes the completed directory with a rename. Model IDs are generated, path-validated, and immutable. Metadata includes source session/version, domain context, row count, per-head results, embedder identity, rule/question versions, parent ID, and `kind: ensemble`. Metrics explicitly carry `evaluation_split: validation`, including model data embedded in stage-five reports.

`list_models(embedder)` compares the complete `{name, model, dim}` identity. A mismatch has `selectable: false` and `다른 임베딩으로 학습된 모델입니다`. Compatibility is also enforced on mode selection, inference, export, and additional training; disabling a UI row alone is not relied upon.

`load(model_id)` caches an evaluated four-member ensemble per storage-root/model-ID pair (bounded process-local cache). Inference invokes those loaded members directly; it does not call T12's `EnsembleResult.predict()` or reconstruct networks per batch.

The train worker selects only `source == human` or `source == agreed && route == accepted`. It constructs features in `Targets.doc_ids` order, joins `JevVote.truncated` as `jev_truncated`, and preserves T12's zero-vector exclusion and human weight of 3. T12 remains the owner of model architecture, deterministic splits, calibration, and training.

A `training.pt` snapshot retains the eligible training features/targets without pickle-only application classes. Additional training loads the parent snapshot, combines it with current eligible labels, lets current documents supersede matching parent document IDs, creates a new model, and leaves the parent unchanged. The snapshot retained with the model excludes rows T12 rejected for zero embeddings.

### Inference and classifier-mode labeling

Predictions contain `tagProbs`, `gradeProbs`, `level`, `confidence`, `predEntropy`, `relevanceScore`, `memberDisagree`, member tag probabilities, signal, and reason. All grade probabilities go through `app.label.rule.grade_probs`; entropy uses natural logarithms. Relevance is exactly `P(core) + P(supporting)`.

Persistent version-local `model_predictions` retain tag probabilities for rule-only recalculation. The version marker triggers recomputation and queue reconciliation without model inference or retraining. Human judgments survive reruns and rule refreshes. LLM-mode predictions do not overwrite agreed labels or suppress subsequent judge-cache merges.

Classifier mode adopts only probabilities strictly below the configured 0.2 cut or strictly above 0.8, with no grade disagreement between members. Boundary/intermediate rows use `model_uncertain`; confident rows with disagreement use `model_disagree`. Missing/zero vectors and unavailable required grade heads also require review. Queues use T11's existing SQLite queue and blind next-item/human-submit APIs.

Inference reads vector shards once, processes bounded batches of 256, and loads the Jev truncation map once per run. It avoids rescanning the vector index and entire vote cache for every batch. Safe checkpoints honor worker stop/pause, and session/version writability is rechecked before persistence.

Worker kinds `train`, `infer`, and `monitor` are registered alongside unchanged `prep` and `judge`. Training schedules inference after saving the model. Stage-four model start schedules inference instead of either full-corpus judge. In classifier mode inference schedules monitoring unless `monitor_rate == 0`.

### Monitoring

A reproducible random sample uses the configured 1% rate, rounding a nonempty corpus upward to one document when needed. Both Jev and GPT use the existing context/question-version cache roots. Only sampled rows are seeded/claimed, already-done votes are reused, cache leases are released, and unrelated pending judge rows are not drained. Monitoring does not merge its votes into classifier labels.

Divergence counts a sampled document once if either judge's grade differs from the model; the report also includes per-labeler divergence, the completed denominator, sampled count, and incomplete count. The warning is present only when divergence is **greater than** 15%:

`이 도메인에서는 LLM 라벨 구간으로 다시 하거나 추가 학습하세요`

Monitoring stores its result in `training.monitor`. If stage five has already been exported, monitoring updates that report by calling the same `export.write_stage5` writer.

### Export and APIs

Exports use the existing `s3.save_jsonl`/`s3.save_json` helpers and write exactly:

- `classified/{sid}/{version}/relevant.jsonl` — Core and Supporting only.
- `classified/{sid}/{version}/all.jsonl` — every prepared document once.
- `sessions/{sid}/versions/{version}/stage_5.json`.

Session `training.exportRef` is the exact relevant-file path; `allRef` records the other file. Exported rows preserve original document fields and guarantee the clustering compatibility fields `title`, `desc`, `cafe`, and `kw`, plus `doc_id`, predicted level, confidence, entropy, relevance, `tagProbs`, signal, source, rule version, and model ID. Human labels override predictions. Export rejects outstanding review items or incomplete document results. Model-free export uses final labels, source, and original label confidence, and writes `model: null`.

`export.write_stage5` is the only new stage-five writer. It combines `app.label.report.label_part(sid)` with optional model metadata/validation metrics and monitoring results.

Registered APIs: `POST /train/{sid}`, `GET /train/{sid}/status`, `POST /train/{sid}/export`, `GET /models`, and `GET /models/{model_id}`. Training accepts optional `parent`; export accepts `withoutModel`. Model listing accepts an optional session/version for exact embedder comparison, otherwise uses the configured embedder. Mutation paths use T11's version/legacy guards and structured error responses.

### Explicit minimal T11 hooks

`routers/labeling_v2.py`:

1. Validate model/embedder compatibility when selecting model mode.
2. Launch only `infer` for model-mode start, record run IDs, and preserve the mode-start lock.
3. Reject legacy full-corpus judge controls in model mode.
4. Project inference/monitor progress in model-mode overview instead of reporting irrelevant Jev/GPT worker progress.

`label/route.py`:

1. Recalculate persisted predictions on rule changes before queue reconciliation.
2. Keep `model_uncertain`/`model_disagree` review rows open rather than treating their zero LLM mismatch flag as approval.
3. Prevent monitor-cache results from replacing model-mode final rows; retain ordinary LLM-mode merges.
4. Mark an explicitly submitted audit as `source: human`, `route: audited`, even when the tags exactly confirm the previous model label. This is necessary for confirmed model labels to enter later training with human weight 3. T11's original unchanged-tags shortcut otherwise left them as `source: model`.

## TDD evidence

RED preceded implementation. The four required test files were written first, including every mandated named test and excluding distillation. Root command:

```text
backend/.venv/bin/python -m pytest backend/tests/model/test_registry.py backend/tests/model/test_infer.py backend/tests/model/test_export.py backend/tests/model/test_model_mode.py -q
```

Initial result: **4 collection errors**, because the registry/infer/export/monitor modules did not yet exist (`task-T13-red.log`). After the minimum implementation, the original tests passed: **15 passed**.

Additional integration RED: **2 failed, 6 passed** (`task-T13-red-integration.log`). The failures exposed the nonexistent `version` field in the worker public-status response and the old legacy service still trying to train. Both were fixed before continuing.

Additional model-overview RED: **1 failed**, because the overview reported completion while inference was running (`task-T13-red-overview.log`). Model-mode progress projection fixed it.

Additional unchanged-audit RED: **1 failed**, because an identical confirmed model audit remained `source: model` (`task-T13-red-audit.log`). The submission hook now marks it human and the test verifies weight 3.

GREEN coverage includes all required names:

- `test_model_mode_zero_llm_calls` — stage-four API start, real loaded fake-weight ensemble inference, overview, and stage-five export; Jev/GPT entry points fail if called; monitoring disabled explicitly.
- `test_rule_change_no_retrain` and persistent-rule-refresh integration.
- `test_registry_embedder_mismatch_not_selectable` and API rejection.
- `test_export_relevant_contract` and `test_export_without_model`.
- `test_model_disagree_routed` and exact 0.2/0.8 boundary cases.
- `test_monitor_divergence_warn` and same-cache sample reuse.
- Target ordering/truncation, missing-vector review, immutable parent snapshots, worker status, unchanged human audit, and preservation of LLM merges after inference.

Refactoring retained passing coverage and removed repeated per-batch corpus/cache scans. Final focused root model run: **38 passed**, one existing Pydantic deprecation warning (`task-T13-green.log`). No network, credentials, or real codex/labeler calls are needed by these tests.

## Required final test commands

- Root cwd `/Users/persona1/Desktop/dcx_agent-dcx2-stage3-5`: `backend/.venv/bin/python -m pytest backend/tests -q` — **1,100 passed, 2 warnings in 114.70s (0:01:54)**.
- Backend cwd `/Users/persona1/Desktop/dcx_agent-dcx2-stage3-5/backend`: `.venv/bin/python -m pytest tests/model -q` — **38 passed, 1 warning in 5.28s**.
- `git diff --check` — passed.

The earlier full run before the final regression additions/refactor passed **1,094 tests**, two warnings, in 114.35s. The final full run is recorded in `task-T13-full-tests.log`; its completed result is listed above. Both required commands exited with code 0.

## Self-review and concerns

1. **Downstream handoff remains outside the allowed ownership.** `services/clustering.py` still reads the old `classified/{sid}/relevant_` prefix and does not consult `training.exportRef`. Moreover, `s3._local_load_data(exact_file)` scans that file's parent directory, so simply passing the new export reference to that helper would combine `all.jsonl` and `relevant.jsonl` and duplicate rows. This task writes the mandated exact paths and verifies their actual contents/field contract, but does **not** claim current clustering consumes those artifacts correctly. The downstream owner must use an exact-file reader and the persisted export reference. Neither downstream file was changed.
2. **Training pause granularity follows T12's existing API.** T12 exposes one `train_ensemble` call with no epoch/member callback. T13 checkpoints before and after that call, and the generic worker heartbeat stays alive during it; pause/stop during training takes effect when that call returns. Training is restartable, but has no mid-epoch checkpoint/resume. T12 files were not modified.
3. **Monitoring definition is explicit.** Either judge differing counts as divergence, and incomplete judgments are separately reported rather than counted as matches. Provider exceptions leave cache-backed work restartable through the generic worker lifecycle; no live-provider or provider-outage test was performed under the no-network constraint.
4. **Existing storage-helper durability is unchanged.** Model directory publication is staged, SQLite writes are transactional, and session updates are atomic. Export helper writes across the two JSONL files and stage report are not one filesystem transaction. Validation occurs before those writes and exportRef is updated last, but an I/O failure during repeat export can leave partially rewritten files until retry.
5. **Legacy API compatibility is deliberately narrow.** The existing `/train` launch/status response shape is unchanged, including its transient in-memory running state. Its service performs only saved-result reads. The legacy status endpoint remains backed by the existing process-local JobManager, so saved results are rehydrated when the legacy `/train` action invokes the reader; this task did not redesign the legacy router.
6. **Test warnings are pre-existing environment warnings:** Pydantic class-based configuration deprecation, plus joblib physical-core detection falling back to logical cores in the full suite.
7. Verified no distillation code/API, no new dependency, no frontend changes, no changes to T12 network/training/calibration code, no direct provider calls on classifier inference/export, and no git commit.

## Fix round 1

Date: 2026-09-30. Branch: `feature/dcx2-stage3-5`. Built on the current T11 fix-round-1 `label/route.py`; only its T13 audit hook and inference lazy import were changed. No network, git write commands, or commits. Parallel T14 files were not modified by this fix.

Changes and minimal choices:

- Limit the unchanged-audit pinning hook to a final row whose source is still `model`. Differing audit answers continue through T10's existing override logic. Unchanged LLM confirmations remain `agreed` / `accepted`, retain the accepted-count input to audit scheduling, and can be re-derived after rule changes. Existing model confirmation coverage still verifies human training weight 3.
- Export uses an accepted/audited/human final label when the selected model prediction is invalid or absent. Preserve the label's level, confidence, signal, and source; set row `modelId`, `tagProbs`, `pred_entropy`, and `relevance_score` to null and add `prediction: "unavailable"`. This explicitly avoids presenting label-derived values as model probabilities. Keep stage-five model metadata for the trained model and preserve ordinary valid-prediction/model-free behavior. Missing predictions use the same fallback as invalid predictions; no usable label/prediction still raises, and open review queues remain blocking. Inference already records vector/head invalidity, so `infer.py` needed no change.
- Check `sqlite_master` for the `inference_context` table before importing `app.model.infer` in queue rebuilds, avoiding torch imports for ordinary LLM label stores.
- Use `meta.get('embedder')` in model listing, marking metadata without an embedder as incompatible instead of raising.

Files changed: `backend/app/label/route.py`, `backend/app/model/export.py`, `backend/app/model/registry.py`, `backend/tests/label/test_route.py`, `backend/tests/model/test_export.py`, `backend/tests/model/test_registry.py`, and this report.

Regression coverage: unchanged LLM audit source/route and accepted count plus subsequent rule rebuild; no inference import without its context table; missing-embedder listing; real inference/export with zero vectors, missing vectors, and an untrained required head, each for agreed/accepted and human/audited labels. Export tests also remove the fallback label and verify rejection. Existing model-audit, valid-model export, model-free export, and T11 label tests pass.

TDD commands and output (repo root):

1. Before implementation: `backend/.venv/bin/python -m pytest backend/tests/model/test_export.py backend/tests/model/test_registry.py backend/tests/label/test_route.py -q` — **9 failed, 10 passed, 1 warning in 2.51s** (`/tmp/t13-fix-red.log`). Seven failures exposed the requested regressions; the two zero-vector cases initially failed in fixture setup because vector IDs cannot be overwritten.
2. Corrected the zero-vector fixture to replace vector artifacts while preserving prepared documents. Temporarily exercised the corrected tests against the original HEAD export implementation, restoring the fix in `finally`: `backend/.venv/bin/python -m pytest backend/tests/model/test_export.py -q` — **6 failed, 2 passed, 1 warning in 2.40s**, exit 1 (`/tmp/t13-fix-red-export.log`). All six fallback cases fail for the intended export behavior.
3. GREEN: `backend/.venv/bin/python -m pytest backend/tests/model backend/tests/label -q` — **241 passed, 1 warning in 8.32s**, exit 0 (`/tmp/t13-fix-green.log`). The warning is the existing Pydantic class-based configuration deprecation.
4. `git diff --check` — passed, exit 0. `git branch --show-current` — `feature/dcx2-stage3-5`.
