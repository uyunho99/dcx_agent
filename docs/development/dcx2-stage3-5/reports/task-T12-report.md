# T12 implementation report

Status: complete. Implemented CPU multitask MLP ensemble training within the assigned model files. No network calls, git write commands, commits, distillation, audit changes, or label/prep test changes were made.

## Exact files

- `backend/app/model/__init__.py`
- `backend/app/model/features.py`
- `backend/app/model/net.py`
- `backend/app/model/train.py`
- `backend/app/model/calibrate.py`
- `backend/tests/model/__init__.py`
- `backend/tests/model/test_net.py`
- `backend/tests/model/test_train.py`
- `.superpowers/sdd/03-plan/task-T12-report.md` (this requested report)

## Implementation

Read the task brief first, design r2 sections 5.1/5.2, VectorStore, label rule, VoteCache, LabelStore, merge, schema, and crawl/preparation document fields.

`build_features` returns float32 arrays of shape `[n,1032]`: Voyage 1024, one-hot channels in naver_cafe/naver_blog/youtube/ppomppu/clien order, log1p(body character count), snippet flag, Jev-truncated flag. Accepts VectorStore, ID mappings, or aligned arrays. Uses actual crawl `source` and `fetch_level` fields, as well as explicit `channel`/`is_snippet` fields. Missing embeddings remain zero without shifting rows. Unknown channels and invalid embedding shapes/nonfinite values fail explicitly.

`MultiHeadMLP` has LayerNorm → Linear(1032,512) → GELU → Dropout(0.2) → Linear(512,256) → GELU → Dropout(0.2). Linear members have an identity body. Heads are anchor(1), sem(6 in rule.SEM order), situation(1), signal(5 in pain/unmet/workaround/delight/none order), reason(4 in ad/no_needs/pure_criticism/other order). `forward` returns logits for numerically stable losses; `probabilities` applies sigmoid to binary heads and softmax to categorical heads.

`masked_loss` uses sample-weighted BCE/CE with independent masks. Anchor uses all eligible rows; sem/situation use anchor-positive rows; signal uses Core/Supporting; reason uses Non. Missing categorical labels are masked. Rare binary tags receive negative/positive-count pos_weight, computed only on the original training fold.

`build_targets` accepts actual final-row dictionaries/sqlite rows. Only accepted agreed rows and human rows enter training. Accepted automatic targets use Jev probabilities and original GPT binary votes from votes_json, rather than merged tags (which can differ from GPT despite matching grades). Human targets are hard with sample weight 3; automatic weight is 1. Signal uses GPT one-hot. Non reason targets average the GPT one-hot with Jev probabilities normalized over the four Non reasons, excluding not_non. VoteCache is opened read-only; ID-to-payload/JevVote mappings are also supported. Rule.grade remains the sole hard-grade implementation, preserving one-semantic-dimension Supporting rows.

`train_ensemble` excludes zero Voyage embeddings, retains filtered doc IDs, and splits deterministically 80/10/10 by grade × channel. Largest-remainder allocation keeps exact global floor(80%)/floor(10%)/remainder sizes while approximating small-stratum proportions. Where LabelStore rows lack channel metadata, it reads the input channel one-hot. Three MLPs have distinct fixed seeds and training-only bootstrap draws; the linear fourth member uses the original training fold. AdamW uses lr 1e-3 and weight decay 1e-4, batches no larger than 256, maximum 30 epochs, patience 3, and restoration of the best validation state. Lower max_epochs is available for small unit tests; values above 30 are rejected.

Heads with fewer than 30 original training-fold eligible documents are zero-initialized, frozen, loss-masked, and marked `trained=False`, `reason=insufficient_samples`. Their head metrics are unavailable. Grade accuracy is unavailable if any necessary binary head is untrained.

`EnsembleResult` exposes four state_dicts, perHead metadata/metrics, member comparison metrics, temperatures, splits, filtered doc IDs, and predict(). Prediction averages member probabilities first; binary means are converted using logit and categorical means using log, then divided by the fitted temperature. Calibration uses only the calibration fold, with one log-temperature parameter per head and LBFGS. A fit that worsens the calibration objective falls back to temperature 1. Semantic labels share one head temperature. Output disagreement includes population standard deviation per head/output and the fraction of member grades differing from the calibrated ensemble grade. Grades use argmax(rule.grade_probs), not a duplicate grade rule.

Metrics use validation hard targets: head accuracy, macro F1, 15-bin confidence ECE, and grade accuracy, plus uncalibrated member comparisons. Semantic F1 averages its six binary outputs; categorical macro F1 covers observed/predicted classes. The ECE implementation supports binary/multilabel and categorical predictions.

## Mandatory TDD evidence

Tests were written before implementation, including every named acceptance test. Both test modules set torch.manual_seed(12) and torch.set_num_threads(2). The learning fixture has 3,000 float32, 1032-dimensional Gaussian documents with different planted directions for all binary tags and categorical classes. All five head F1 values and grade accuracy must reach at least 0.9.

Initial RED command, from repository root:

```text
backend/.venv/bin/python -m pytest backend/tests/model -q
FFFFFEFFEFF                                                              [100%]
9 failed, 1 warning, 2 errors in 0.66s
```

Failures were ModuleNotFoundError for app.model.net/train/calibrate/features, as expected before implementation. test_forward_shapes (both architectures), test_mask_zero_grad, test_soft_targets, test_one_dim_doc_is_supporting_and_trained, test_temperature_reduces_ece, test_head_min_samples, and two feature/filter tests failed. test_ensemble_learns_synthetic and test_seed_reproducible errored at synthetic fixture setup because app.model.train was missing.

First GREEN, same command after minimum implementation:

```text
...........                                                              [100%]
11 passed, 1 warning in 3.86s
```

During integration self-review, added real VectorStore/VoteCache coverage and small-stratum/missing-label coverage. The real crawl schema regression was first observed RED:

```text
backend/.venv/bin/python -m pytest backend/tests/model/test_train.py::test_real_store_contracts -q
F                                                                        [100%]
FAILED backend/tests/model/test_train.py::test_real_store_contracts - KeyError: 'channel'
1 failed, 1 warning in 0.46s
```

Corrected feature ingestion to recognize source/fetch_level. Also refined channel recovery from features and suppressed grade metrics when grade heads are untrained.

Final required root invocation:

```text
backend/.venv/bin/python -m pytest backend/tests/model -q
.............                                                            [100%]
13 passed, 1 warning in 3.42s
```

Final required backend invocation:

```text
cd backend && .venv/bin/python -m pytest tests/model -q
.............                                                            [100%]
13 passed, 1 warning in 3.86s
```

Both complete well within 60 seconds on CPU. The sole warning is the existing Pydantic class-based Config deprecation in app/config.py. `git diff --check` returned no output; new model files remain untracked because committing/staging was prohibited. No broad unrelated suite was run.

## Self-review and integration concerns

- Verified masked semantic targets cannot change gradients for masked rows, both member architectures and probability normalization, original-GPT soft targets, human weights, Supporting inclusion, training-head exclusion, fixed-seed state equality, calibration ECE improvement, exact split sizes/disjointness, grade × channel proportions, missing categorical labels, real cache reads, reordered/missing vector alignment, and zero-vector exclusion.
- Callers must build features in `Targets.doc_ids` order after accepted/human filtering. The API documents this rather than silently guessing correspondence from equal array lengths. Returned split indices address the returned filtered doc_ids.
- Callers must join JevVote.truncated into each feature document as jev_truncated; build_features has no cache parameter. Crawl fetch_level supplies the snippet flag automatically.
- LabelStore final rows do not contain channels. Either join channel metadata before build_targets or provide valid channel one-hot features; training now rejects missing/invalid channel information instead of silently stratifying only by grade.
- Downstream routing must honor perHead.trained. Frozen heads still expose neutral probabilities for a stable output shape; those probabilities are not learned evidence.
- Metrics are validation metrics from the same fold used for early stopping; this contract has no separate untouched test fold. Calibration data remain separate from training and early stopping.
- Extremely small strata cannot occupy every fold; allocation preserves global proportions deterministically. Minimum-head eligibility is measured on the original training fold, not total labels or bootstrap duplicates.
- Synthetic performance verifies learnability, not production accuracy. The implementation loads aligned training arrays and does not add an out-of-core training worker, persistence registry, inference module, API, or distillation (outside T12 ownership/scope).
- No blocking concerns remain. The existing Pydantic warning is unrelated to T12.
