# Task T3 report

- status: complete
- executor: codex
- branch: feature/dcx2-stage6-8

## Files

- `backend/app/segment/l1.py` — Ward sample and k scan, full/streaming clustering, size-ordered labels and centers.
- `backend/app/segment/ctfidf.py` — shared class-based TF-IDF keyword ranking.
- `backend/tests/segment/test_l1.py` — 12 offline deterministic tests.
- `.superpowers/sdd/03-plan/task-T3-report.md` — this report.

## RED evidence

Wrote tests before creating either implementation module. Ran:

`backend/.venv/bin/python -m pytest backend/tests/segment/test_l1.py -q`

Result: exit 2, collection error, `ImportError: cannot import name 'l1' from 'app.segment'`; 1 error in 0.84s.

First implementation run: 10 passed, 1 failed in 3.56s. The centroid alignment test differed from a separately accumulated mean by 1.37e-6 due to float32 summation. Adjusted its absolute tolerance from 1e-6 to 3e-6; cluster sizes and center-to-label alignment remain checked. Added a corpus-frequency ranking regression test.

## GREEN evidence

`backend/.venv/bin/python -m pytest backend/tests/segment/test_l1.py -q`

Result: **12 passed**, 2 warnings, 3.34s, exit 0.

Coverage includes the committed session fixture through `load_input`, expected k=5, inclusive 3..8 scores, exact real Ward merge summary, repeatability, 20,000-row random sample cap, float32 sample/batch contracts, forced MiniBatch path with exact 4096/4096/1808 batch sizes, repeatable streaming labels/centers, size-descending IDs with reordered centers, c-TF-IDF distinctiveness and corpus term frequency, empty groups and short inputs.

## Full-suite result

`backend/.venv/bin/python -m pytest backend/tests -q`

Run once: **1508 passed, 1 deselected, 2 warnings in 145.68s (0:02:25)**. No test failures, including no environment/sandbox-only failures. Warnings are listed below.

## tracemalloc peak

Measured with:

`backend/.venv/bin/python -m pytest backend/tests/segment/test_l1.py::test_large_input_streams -q -s`

Result: **1 passed**, 2 warnings, 1.89s. Peak: **5,446,773 bytes (5.19 MiB)** during `cluster` on **200,000 × 64 float16** synthetic rows, with five groups. Input construction precedes tracing. The test checks five recovered clusters, perfect adjusted Rand agreement, and peak allocation below the 51,200,000 bytes required for a full float32 input copy. The measurement is traced allocation, not process RSS or a guarantee that every native-library allocation is tracked. The test also records the peak as a pytest property.

## Self-review

- Read the requirements brief first, then the prior-task interfaces and design section 3.2. All thresholds come from `params`; no parameter values changed.
- Selected k is the maximum silhouette (smaller k wins ties); inertia values provide the elbow display. Ward and silhouette receive the same float32 sample, never the full input above WARD_SAMPLE.
- Large-input training makes one deterministic shuffled pass with `partial_fit`, `batch_size=4096`, `n_init=5`, and predicts in original document order in float32 batches. No full float32 input copy is made. Small-input KMeans uses `n_init=10`.
- Returned integer label i directly identifies CL{i}; centers are reordered with labels. Equal-size groups retain deterministic model-label order. MiniBatch centers retain estimator semantics.
- c-TF-IDF uses normalized class term frequency multiplied by log(1 + mean class token count / corpus term count); tokens are not split or otherwise rewritten. Lexical ordering settles equal scores.
- Refactor review retained the compact shared shape/seed checks and single final renumbering step; no additional abstraction was necessary after GREEN.
- No network calls, subagents, git add, or git commit. Only owned files and this report were written.

## Concerns

- Exact Ward remains quadratic in sample size: at the mandated 20,000-row cap its float64 condensed distances alone are approximately 1.49 GiB. The cap test instruments Ward/silhouette to avoid allocating those matrices; the smaller integration test exercises both real algorithms. Production-size Ward runtime/RSS has not been benchmarked here.
- The streaming memory test uses 64 dimensions; the committed session integration uses 1024 dimensions. No claim is made that the 5.19 MiB measurement applies at 1024 dimensions.
- Identical/degenerate input can produce fewer distinct clusters than requested, as with sklearn; undefined sample silhouette is recorded as -1.0. Inputs with fewer than four rows cannot score any k in the mandated range and raise ValueError.
- Environment warning: joblib cannot parse the physical core count in this sandbox and falls back to logical cores. Existing Pydantic deprecation warning also appears. Neither warning fails the T3 tests.
