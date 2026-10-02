# T16 — Offline integration and performance

Status: complete. New integration tests, opt-in performance test, and the full backend suite passed.

## Changes

- Added `backend/tests/evidence/test_integration.py::test_stage5_to_stage7_offline`: `make_evidence_session` creates 72 synthetic stage-five documents, runs real stage six with fake LLM responses, and confirms all layers. TestClient then exercises POST run, status polling, every Context's all/new tabs, POST Known Insight, refresh-new, and GET package.
- The real router, `runner.start/status`, worker SQLite lifecycle, `worker.execute`, registered evidence entry, pipeline, and stores execute unchanged. Only the runner's subprocess launch is replaced with a joined in-process thread so deterministic LLM/embedding fakes and socket guards apply to worker execution. Detached OS-process startup itself is outside this test's scope.
- Validates the returned and persisted `EvidencePackage`, nonempty Context evidence with verified quotes, `stage_7.json` design 4.8 fields/types/counts/coverage/parameters, worker completion/progress, and the session API's `segmentDone` and `evidenceDone` flags.
- Guards both socket `connect` and `connect_ex`, records attempted connections, and asserts zero attempts. The existing global external-socket guard remains unchanged.
- The ordinary second run makes **zero LLM calls**, changes the evidence run ID, and preserves cached tags. An additional `fresh=True` run forces recomputation and makes **zero tagging calls**, while queries and novelty regenerate and tag-cache hits are recorded. This distinguishes checkpoint resume from actual tag-cache reuse.
- Adding a Known Insight through POST `/known/{sid}` marks Contexts changed; refresh-new excludes the handed document, preserves all-tab items, makes zero LLM calls, and leaves a valid package and completion state.
- Added `test_confirm_all_script_runs_evidence_api`: executes the actual `make_segment_qa.py --confirm-all` CLI parser/defaults via `runpy` under the same network guard, confirms its 1,200-document output, and runs that session through the evidence API/worker to a validated package and completion.
- Added `backend/tests/evidence/test_perf.py`, marked `perf`, following bundle one's marker convention. Existing `backend/pytest.ini` already registers `perf` and defaults to `-m "not perf"`; no configuration changes were needed.

## Performance measurement

Command: `backend/.venv/bin/python -m pytest backend/tests/evidence/test_perf.py -m perf -q -s`

Result: **1 passed, 1 warning in 0.07s**.

Deterministic seed 42; 31 Contexts × 50 candidates; 1,024-dimensional normalized vectors. Input generation is outside the timers. Tabs include real all/new selection and one handed Known Insight exclusion per Context. Both tabs return ten items. No timing threshold is enforced. Values are printed and attached as pytest record properties.

| Operation | Total | Per Context |
| --- | ---: | ---: |
| Rerank (`rerank.select`) | 0.005261 s | 0.000170 s |
| All + new tabs (including reranking) | 0.019675 s | 0.000635 s |

These are local CPU measurements, excluding retrieval, LLM calls, HTTP, persistence, and setup; they are not end-to-end latency estimates.

## Verification

- Targeted integration: `backend/.venv/bin/python -m pytest backend/tests/evidence/test_integration.py -q` — **2 passed, 2 warnings in 20.96s**.
- Full backend: `backend/.venv/bin/python -m pytest backend/tests -q` — **1946 passed, 3 deselected, 2 warnings in 336.94s (0:05:36)**. Run once after the targeted checks; opt-in performance tests were excluded by default.
- `git diff --check` passed.

## Findings and concerns

No production bug requiring a fix was exposed; production files and frontend are unchanged. Initial red runs corrected test-harness assumptions: subprocess replacement must be scoped to the runner, stage-six invalidation can remain `stale` briefly while the worker loads, and the session endpoint nests completion under `data`.

The targeted runs and full suite emitted existing Pydantic configuration deprecation and sandbox CPU-detection fallback warnings. Performance numbers are observations without thresholds. No files were staged or committed.
