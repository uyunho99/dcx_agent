# T11 report — evidence worker, resume, versions, completion

Status: implemented. All identified failures were corrected and affected tests pass. The full backend suite was run exactly once; its original result and subsequent focused verification are distinguished below.

## Implementation

- Created `backend/app/evidence/pipeline.py`. It loads confirmed segment rows, prepared original documents, exported tag probabilities, vectors and cached dims; generates Persona queries; prepares Persona support; processes Context search, tagging, all/new selection, coverage supplements, expansion and novelty; publishes the package and `stage_7.json` through T10 assembly.
- Added the `evidence` worker kind and `settings.evidence_llm_concurrency: int = 4`. Context work uses `ThreadPoolExecutor(max_workers=concurrency)`. Tag batches execute through T7 on the worker main thread, with provider work in bounded pools. A shared semaphore caps provider concurrency across tagging and novelty. Evidence, tag and dims SQLite writes remain on the worker main thread.
- Context `done`/`skipped` rows are durable checkpoints. `checkpoint.json` also retains query/Persona progress and tagging counters. Resume skips completed Contexts and rotates the run UUID; fresh resets replace evidence rows. `queries.json`, `llm_calls.json`, `package.json` and `stage_7.json` are persisted. Resuming with a changed concurrency setting records the current value without repeating completed LLM work.
- One Context exception writes `failed` with its reason and permits other Contexts to finish. Incomplete runs publish session status `partial`; skipping all failed rows permits `done`. Provider-only backend/timeout failures interrupt with the exact stage-six `LLM_REASON`. Cooperative stops also remain interrupted and resumable. Heartbeats carry Context/tag-batch progress and cumulative tag calls.
- Pending Contexts read current Known Insights. Completed Contexts carry `counts.knownChanged` when additions invalidate their input snapshot. Deletion drops cached Known pairs and recomputes affected completed new tabs without LLM calls. A regression fixes edits between tab selection and novelty: a later Known read cannot relabel earlier selection as having incorporated that edit.
- Exposed `refresh_new(sid, version, context_id, run)` and `skip_context(sid, version, context_id, run)`. Both check the current generation and writable version under the session lock. Refresh uses cached tags and returns the T12 Context response fields, preserving all-tab selection and saved call totals. Skip accepts failed rows and updates the checkpoint and completion state. Skip during an active run is rejected.
- A fresh stage-six reset sets `session.evidence = {'status': 'stale'}` and removes cached `completion.evidenceDone`. Stage-seven version restart preserves segment confirmations, removes evidence artifacts and removes that completion field; shared tag caches survive. `compare(stage7)` returns `{same, before, after}`, with report metrics and Context `selectedAll`/`selectedNew` IDs.
- Server completion now includes `evidenceDone = evidence.status == 'done' and 'stage7' not in stale`.

## Tests and results

TDD began by writing `backend/tests/evidence/test_pipeline.py` and `backend/tests/context/test_versions_stage7.py`. The initial run failed during collection because the evidence pipeline did not exist. Implementation then passed the brief's lifecycle, failure, concurrency, Known-change, stale-action, heartbeat, restart, cache and completion cases. Additional regressions were observed failing before fixes for report-call preservation, late Known additions/deletions, and concurrency metadata on resume.

Required full-suite command, executed exactly once:

```text
backend/.venv/bin/python -m pytest backend/tests -q
13 failed, 1906 passed, 2 deselected, 2 warnings in 309.58s (0:05:09)
```

All 13 failures were identified and corrected:

- Twelve parameterized cases in `tests/context/test_session_completion.py` expected the old exact completion dictionary. Its four assertions now include `evidenceDone=False`, preserving their existing assertions and read-only checks.
- `tests/test_review_fix1.py::test_g6_environment_documentation` required the new setting in the environment documentation. Added `EVIDENCE_LLM_CONCURRENCY` to `README.md` and `.env.example`.

Post-fix verification:

```text
backend/.venv/bin/python -m pytest backend/tests/evidence backend/tests/context backend/tests/test_review_fix1.py -q
433 passed, 2 warnings in 36.46s
```

After the final concurrency-on-resume metadata fix:

```text
backend/.venv/bin/python -m pytest backend/tests/evidence/test_pipeline.py backend/tests/context/test_versions_stage7.py -q
42 passed, 2 warnings in 10.08s
```

An earlier broader pipeline/assembly/segment/stopwords run also passed 80 tests. Tests use fake LLM responses and embeddings with the existing network block intact. The new integration test feeds real confirmed stage-six fixture outputs into the actual stage-seven modules. Concurrency tests check selection parity, overlapping calls within the configured cap, Context pool execution, and caller-thread cache publication. Both refresh and skip reject old run IDs; stage-six reset invalidates existing refresh clients.

`git diff --check` passes. Warnings were the existing Pydantic class-config deprecation and joblib physical-core detection warning. One intermediate focused run was interrupted to correct a regression-test injector that accidentally repeated its simulated Known edit during cache-only refresh; the corrected injector fires once, and both cases pass.

## T12 handoff and concerns

Query owners use `persona:{id}` and `context:{id}`. Per-row UI metadata lives in `contexts.counts`, including `knownChanged`, `knownIds`, `excludedKnown`, `query_gen_fail`, and the assembly counters. `refresh_new` returns Context/new-tab views; `skip_context` returns the updated session evidence status, which T12 can combine with stored Context rows for its status response. `partial` is intentional under D-252 despite the older completion-contract enum omitting it.

No known implementation blockers remain. A clean post-fix full-suite result is not claimed: the full suite was not repeated because the task explicitly requested one full run. All failures from that run passed in the affected-suite verification; the final metadata change passed the 42-test pipeline/version run.

Additional files beyond the brief's primary implementation files are the existing completion assertions and the two environment documentation files required by the full-suite contract. No frontend files were changed. No subagents were used. Nothing was staged or committed.
