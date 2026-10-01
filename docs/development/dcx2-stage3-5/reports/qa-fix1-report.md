# Browser-QA backend fix report — 2026-09-30

Requirements: `.superpowers/sdd/03-plan/qa-fix1.md`, the browser QA report dated 2026-09-30, and decision R-112.

## Scope

Edited only `backend/` and this report. No commits, package installs, or frontend edits. Frontend changes appearing in the shared working tree belong to the parallel job.

## Per-item RED / GREEN evidence

All commands below ran from the repository root using `backend/.venv/bin/python -m pytest`.

### Q1 — server-selected preparation default

- RED: `backend/tests/prep/test_prep_api.py -q -k qa_q1` → **1 failed** (`KeyError: config`).
- GREEN: `backend/tests/prep/test_prep_api.py -q` → **9 passed**.
- `PrepConfig` already used `settings.embed_backend`; exposed the resolved configuration as `GET /prep/{sid}/status.config`, including `config.embedder`. The test loads `EMBED_BACKEND=fake`, checks the exposed default, runs preparation without saving a choice, and verifies successful completion with `fake` persisted.
- Files: `backend/app/routers/prep.py`, `backend/tests/prep/test_prep_api.py`.

### Q2 — preserve evidence when the answer model is unavailable

- RED: `backend/tests/test_browser_qa.py -q` → **10 failed** (error status instead of ok; old message).
- GREEN: `backend/tests/test_browser_qa.py backend/tests/known -q` → **41 passed**.
- Both `/chat` and `/insight-chat` return `status: "ok"`, the original `sources` and `reason`, and exactly `답변 모델이 연결되지 않아 근거 원문만 보여 줍니다.` when the model returns `None` or an empty string for a session request. Insight chat retains `modified: false`.
- Requests omitting `sid` retain their legacy error status and empty sources; only the message changes. Tests cover both routes, both empty model responses, nonempty evidence, empty evidence with `all_known`, and requests omitting `sid`.
- Files: `backend/app/routers/chat.py`, `backend/tests/test_browser_qa.py`.

### Q4 — actual inference and monitoring counts

- RED: `backend/tests/model/test_model_mode.py -q -k qa_q4` → **3 failed** (`KeyError: done`); additional monitor heartbeat regression → **1 failed** (`KeyError: done`).
- GREEN: `backend/tests/model backend/tests/label backend/tests/test_final_fix1.py -q` → **277 passed**.
- Inference and monitor heartbeats persist exact counts. The overview exposes these alongside existing worker state and progress. Tests exercise running/completed projections and real inference/monitor worker heartbeats, including monitor samples with unavailable votes.
- Exact response fields: `GET /label/{sid}/overview.progress.infer` and `.progress.monitor` now include **`done`, `total`, `pending`, `bad`, `estimate`, `reason`**, alongside **`state`, `progress`, `runId`** and existing run metadata. `pending = max(total - done, 0)`. `done` counts processed documents/samples; monitoring `bad` reports incomplete samples at completion. Worker **`detail.done`** and **`detail.total`** persist these values; monitor results also persist **`training.monitor.done`** and **`training.monitor.total`**. Existing completed runs can use their `detail.n` / `detail.sampled` counts.
- Files: `backend/app/model/infer.py`, `backend/app/model/monitor.py`, `backend/app/routers/labeling_v2.py`, `backend/tests/model/test_model_mode.py`.

### Q5 — actual embedder display name

- RED: prep / registry / training tests selected by `-k 'qa_q5 or test_train_worker_and_parent_snapshot'` → **3 failed** (prep reported `voyage-4`; registry lacked `embedderName`; training lacked `embedder`).
- GREEN: `backend/tests/prep backend/tests/model backend/tests/vectors backend/tests/known -q` → **131 passed**.
- Follow-up RED: `backend/tests/prep/test_prep_api.py -q -k qa_q5_reused` → **1 failed** (an existing completed report still displayed `voyage-4`). Status/run projection now reads the actual backend identity from the prep manifest, including reused pre-R-112 artifacts, without rewriting historical files. Follow-up GREEN: `backend/tests/prep -q` → **38 passed**; final full-suite result is below.
- Display names use `fake` for the fake backend and the configured model name for Voyage. The backend identity tuple remains unchanged for existing cache/model compatibility; its `model` value is a compatibility setting, not the fake backend's display label.
- Exact fields: prep **`manifest.json.embedderName`** (new), existing **`manifest.json.embedder.name`** (already actual backend), and **`stage_3.json.embedder`** / **`GET /prep/{sid}/status.stage3.embedder`** (corrected string). Training adds **`GET /train/{sid}/status.training.embedder`** (`name`, `model`, `dim`) and **`training.embedderName`**. Model registry **`meta.json.embedderName`**, **`GET /models.models[].embedderName`**, and **`GET /models/{model_id}.embedderName`** are new; existing **`embedder.name`** remains available. Fake display names are exactly `fake`.
- Files: `backend/app/routers/prep.py`, `backend/app/vectors/embedder.py`, `backend/app/prep/pipeline.py`, `backend/app/model/registry.py`, `backend/app/routers/training_v2.py`, `backend/tests/prep/test_pipeline.py`, `backend/tests/prep/test_prep_api.py`, `backend/tests/model/test_registry.py`, `backend/tests/model/test_model_mode.py`.

### Q6 — reuse only previously completed results

- RED: `backend/tests/prep/test_prep_api.py -q -k qa_q6` → **1 failed** (`KeyError: reused` on completed status).
- GREEN: `backend/tests/prep backend/tests/test_review_fix1.py -q` → **64 passed**.
- Persist the actual reuse decision and expose **`reused`** in both run and status responses. Reset it when changing config or starting fresh work; publication of a newly built result records false, completed-result reuse records true.
- Regression creates a real embedding failure after docs and tokens were written, switches to fake, verifies first success is not reuse, then verifies a repeated completed result is reuse and config edits clear the flag.
- Files: `backend/app/routers/prep.py`, `backend/app/prep/pipeline.py`, `backend/tests/prep/test_prep_api.py`.

### Q8 — no training badge for a completed latest run

- RED: **not reproduced in this checkout**. The existing `session_activities` implementation already selects the latest run per kind/labeler before excluding `done`; existing tests also cover completed replacements. No production change was needed, and no artificial failure was introduced.
- Added the requested regression before considering a code change: `backend/tests/context/test_t15_fix1.py -q -k qa_q8` → **4 passed immediately**. It verifies a completed training run alone and after failed, interrupted, or previously running predecessors, including `/sessions.activity`.
- GREEN: `backend/tests/context -q` → **114 passed**.
- File: `backend/tests/context/test_t15_fix1.py`. Existing implementation: `backend/app/context/store.py` (unchanged).
- This is the sole exception to a demonstrated RED-first cycle: the required backend behavior was already fixed.

### Q11 — historical grade mismatch rate

- RED: `backend/tests/label/test_label_api.py -q -k qa_q11` → **1 failed** (`0.75` instead of `0.5`, because a labeler failure was incorrectly included).
- GREEN: `backend/tests/label -q` → **197 passed**.
- Numerator now counts `grade_mismatch` queue records across all statuses, including resolved records, rather than all currently open review items. Denominator remains `merged`. Regression checks 2 mismatches / 4 merged documents before and after all reviews, with an unrelated labeler failure excluded.
- Files: `backend/app/label/overview.py`, `backend/tests/label/test_label_api.py`.

## Final verification

Initial full required command: `backend/.venv/bin/python -m pytest backend/tests -q` → **1,278 passed, 2 warnings in 128.63s**. Final rerun after the Q5 reused-artifact correction: `backend/.venv/bin/python -m pytest backend/tests -q` → **1,279 passed, 2 warnings in 130.49s**. Exit code 0.

`git diff --check -- backend .superpowers/sdd/03-plan/qa-fix1-report.md` also passed. Backend work is complete; Q8 was already implemented and is now explicitly covered by additional regressions.

Warnings observed in focused runs: existing Pydantic class-based configuration deprecation; joblib physical-core detection fallback. No dependencies installed. Browser UI verification belongs to the parallel frontend/controller QA pass.
