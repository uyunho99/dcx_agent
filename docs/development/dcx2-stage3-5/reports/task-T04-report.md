# Task T04 report — 3단계 파이프라인

Status: implemented; focused and affected regression tests pass. No commit or git write commands were performed. T06-owned files were not edited.

## Implementation

- Added `PrepConfig` with the required defaults: `minBodyChars=10`, analyzer `kiwi`, POS `NNG/NNP/VV/VA/XR`, model `voyage-4`, dimension 1024, configurable advertisement/source filters and channel phrase dictionaries. Embedding backend defaults follow T01 settings.
- Added deterministic `p_` + 12 hex SHA-256 preparation keys. Canonical JSON includes collection ID, sorted/deduplicated rule lists and dictionary contents, actual embedder name/model/dimension, and installed Kiwi version. Rule list ordering does not invalidate equivalent results.
- Added HTML/entity cleanup, channel phrase removal and occurrence counts for body and individual comments, and Unicode punctuation/symbol removal exclusively for token input. Kiwi emits only the requested POS forms.
- Reused `_crawl_docs` and its child-first collection inheritance/deduplication. Its optional session snapshot binds a worker to the explicitly requested version instead of the changing active pointer.
- Extracted existing D-084–086 filtering into a shared function. Legacy acceptance and advertisement behavior remain unchanged. New preparation checks the complete cleaned body/comments, including text beyond the compatibility `desc` 4,000-character cap. Full-document length remains body-only; snippet title/description exceptions remain intact. There is no target-word filter.
- Added `run_prep(ctx, sid, version)` without registering a worker kind. Configuration is read from the requested version's `prep.config`; optional `ctx.args['config']` overrides support the service bridge and simple fake contexts.
- Writes `derived/{sid}/{collectionId}/{prepKey}/`: 5,000-row document/token parts, 10,000-row vector work shards through T02 `VectorStore`, float16 storage, manifest metadata/progress, and exact stage-three report fields. Embedding input is title + body + comments, capped at 2,000 characters, in batches of at most 128.
- Failed/invalid/zero provider rows are attempted up to three times; successful rows are retained and only unsuccessful rows are retried. Exhausted failures become zero vectors and explicit failed index entries/report counts. Provider exception payloads are not persisted.
- Added atomic manifest/docs/tokens/report writes, a per-preparation writer lock, completed-shard skipping, pause/stop checkpoints, and recovery when vector publication succeeded but progress publication did not. A done result avoids collection reads and embedding calls.
- Publishes the compatibility JSONL through the existing `services.preprocessing.save_jsonl` connection, using a stable timestamp filename and durable completion marker for retry. Publishes the derived reference into the requested version under the session lock. New sessions use the pipeline; legacy sessions use the prior path.

## Exact files created

1. `backend/app/prep/__init__.py`
2. `backend/app/prep/config.py`
3. `backend/app/prep/boilerplate.py`
4. `backend/app/prep/clean.py`
5. `backend/app/prep/tokens.py`
6. `backend/app/prep/pipeline.py`
7. `backend/app/prep/report.py`
8. `backend/app/prep/boilerplate.v1.json`
9. `backend/tests/prep/test_pipeline.py`
10. `.superpowers/sdd/03-plan/task-T04-report.md`

## Exact files modified

- `backend/app/services/preprocessing.py`

## TDD evidence

### Required RED before implementation

All nine named acceptance tests were written first:
`test_filters_use_body`, `test_no_target_word_filter`, `test_boilerplate_removed_counted`, `test_two_paths`, `test_tokens_written`, `test_prep_key_reuse`, `test_embed_failure_zero_vector`, `test_resume_skips_done_shards`, `test_stage3_report_contract`.

Command:

```text
cd backend && .venv/bin/python -m pytest tests/prep -q
```

Output / exit:

```text
E   ModuleNotFoundError: No module named 'app.prep'
ERROR tests/prep/test_pipeline.py
1 warning, 1 error in 0.08s
exit 2
```

This was the expected missing implementation failure. The first implementation run then produced `9 failed, 1 warning in 0.99s`: the test fixture incorrectly used `part-00001.jsonl` for crawl input, whereas the existing crawl reader requires `shard-*.jsonl`. Correcting the fixture filename, without changing assertions, produced:

```text
......... [100%]
9 passed, 1 warning in 1.66s
exit 0
```

### Additional RED / GREEN and refactor

Added cache IO, post-vector-publication crash recovery, provider zero-result retry/batch size/truncation, explicit version snapshot/publication, pause/empty input, cleaner/default/key sensitivity, unconnected-provider preservation, and document/vector boundary tests.

The cache regression initially failed for the expected reason:

```text
FAILED tests/prep/test_pipeline.py::test_done_cache_does_not_read_collection_again
AssertionError: completed cache must return without collection IO
1 failed, 14 passed, 1 warning in 5.03s
```

Moving collection IO after the done-cache check produced `15 passed, 1 warning in 5.02s`.

Final standalone focused command before the compatibility-export regression correction:

```text
cd backend && .venv/bin/python -m pytest tests/prep -q
................. [100%]
17 passed, 1 warning in 4.85s
exit 0
```

Initial integration regression command:

```text
cd backend && .venv/bin/python -m pytest tests/test_integration_stage0_2.py -q
36 passed, 2 warnings in 6.65s
exit 0
```

### Full suite — executed once as requested

```text
cd backend && .venv/bin/python -m pytest -q --ignore=tests/label/test_jev.py
FAILED tests/crawl/test_final_w5.py::test_finish_partial[blocked]
FAILED tests/crawl/test_final_w5.py::test_finish_partial[parse_error]
2 failed, 870 passed, 2 warnings in 103.18s (0:01:43)
exit 1
```

Both failures checked the existing `preprocessing.save_jsonl` export connection. The initial pipeline exported directly with an atomic local write, bypassing that connection. Refactored compatibility publication to reuse `save_jsonl`, with a manifest completion marker to recover interrupted exports.

Post-correction validation (includes both failures, all prep tests, and the required stage 0–2 integration suite):

```text
cd backend && .venv/bin/python -m pytest tests/prep tests/crawl/test_final_w5.py tests/test_integration_stage0_2.py -q
................................................................. [100%]
65 passed, 2 warnings in 10.26s
exit 0
```

The full suite was not rerun; its one recorded run remains 870 passed / 2 failed, with both failures subsequently corrected and individually covered by the passing 65-test run. Do not describe this as a final 872-pass full-suite run.

`git diff --check` passed after the final implementation change. Existing warnings concern Pydantic class-based config deprecation and joblib physical-core detection.

## Self-review

- Confirmed ownership boundaries: only the eight prep module/data files, one prep test file, existing preprocessing service, and this requested report were written. Concurrent label/schema/question/Jev work was left untouched.
- Confirmed all nine brief test names exist and pass, along with eight additional tests.
- Confirmed 128-row requests, 2,000-character truncation, 1024-dimensional defaults, float16 vector bytes, separate punctuation-preserving docs/embedding and punctuation-free token paths, report keys, cache reuse, zero-vector flags, and two-completed-shard resume behavior.
- Confirmed partial vector publication does not duplicate IDs or call the embedder again on restart.
- Confirmed a v2 worker can read/write v2 while the active pointer remains v1; compatibility docs match derived docs.
- Confirmed existing stage 0–2 integration behavior, including no-key runs, child-first collection merging, snippets, desc limits, and legacy outputs.
- No worker-kind registration, router changes, dependency installation, network research, or commits were added.

## Concerns / limitations

1. **Unconnected Voyage compatibility:** existing integration tests require new-session preprocessing to finish without API keys. An `EmbedderUnconnected` factory failure is therefore represented by the configured Voyage metadata plus explicitly failed zero-vector rows, rather than aborting document preparation or silently substituting fake vectors. Those failures are visible in `stage_3.json` and vector index flags. A done preparation is immutable and reused by key; adding credentials later does not automatically recompute failed vectors. A future explicit retry/invalidation operation belongs outside this task.
2. **Full-suite evidence:** the single full run had the two export-connection regressions described above. Both now pass within the final affected 65-test run, but there is no post-fix full-suite run because the instruction specified running it once.
3. **Dictionary provenance:** the initial dictionary includes the design's café membership wording and blog UI phrases. `이웃추가` was verified in the recorded blog HTML fixtures; the café phrases are conservative starter entries, not claimed to be extracted from a recorded café response. The dictionary remains editable through preparation configuration.
4. **Scale:** `_crawl_docs` intentionally retains its existing whole-collection materialization, and cleaning/filtering also holds the document list in memory. No million-document memory/performance benchmark was performed. Worker pause/stop is cooperative at vector work-shard boundaries (10,000 accepted documents), so an in-progress shard finishes before honoring a newly requested stop.
5. **Counting semantics:** original/duplicate counts apply after the existing crawl reader's child-first/doc-ID deduplication; duplicates already removed by that reader are not counted again.
6. **Embedding settings:** a requested model/dimension that differs from the actual T02 embedder configuration is rejected instead of silently producing mislabeled vectors. T01 defaults satisfy the required voyage-4 / 1024 contract.
7. **Compatibility export:** the existing `save_jsonl` writer itself is not atomic. The completion marker allows an interrupted export to be overwritten on retry; derived docs, tokens, reports, and vector publication use durable writes independently.

## Fix round 1

### Changes

- Removed the `_Unconnected` fallback. Embedder construction now propagates `EmbedderUnconnected` before creating preparation/vector output; an unconnected error raised during embedding also propagates instead of becoming a zero vector. Such a run cannot publish a done manifest. Reconnecting with the same provider metadata/configuration computes vectors under the same prepKey.
- Before resuming unfinished preparation, retry persisted failed rows once through the existing three-attempt embedding policy, including rows in work shards already marked complete. Preserve successful rows, document IDs, shard row layout, and the done-cache early return. Recompute report counts from the updated stored failure flags.
- Replace affected vector shard bytes atomically before atomically publishing updated failure flags. Interruption between these writes leaves rows marked failed and retryable; successful rows remain intact. No VectorStore API changes were needed.
- This supersedes the original report's concern 1: missing Voyage credentials must stop preparation, rather than complete with cached failed vectors.
- Only `backend/app/prep/pipeline.py`, `backend/tests/prep/test_pipeline.py`, and this report were edited. No router, worker, label, or report-count module changes; no network, git writes, or commits.

### Covering tests

- Replaced `test_unconnected_keeps_documents_with_explicit_failure` with `test_unconnected_stops_without_vectors_and_can_resume`, covering both constructor-time and embedding-time disconnection: raises, no done manifest or stored vectors, then same-key completion using a fake-backed Voyage-identity embedder with nonzero vectors.
- Added `test_resume_retries_failed_rows_in_completed_shard`, covering recovery and repeated real failure: initial batch exhausts three attempts, run interrupts before done, resume only retries the failed row, preserves the successful vector and row count, updates embedded/failure counts, and does not retry a done result.
- Added `test_retry_interrupted_before_failure_flags_are_published`: interruption during retry publication remains recoverable without duplicate rows.
- Existing tests continue to cover successful shard skipping, publication-before-progress crash recovery, batch limits, three-attempt zero fallback, docs/tokens, cache reuse, and prep API behavior.

### RED

Command:

```text
cd backend && .venv/bin/python -m pytest tests/prep -q
```

Output (before pipeline changes):

```text
FAILED tests/prep/test_pipeline.py::test_unconnected_stops_without_vectors_and_can_resume[factory]
FAILED tests/prep/test_pipeline.py::test_unconnected_stops_without_vectors_and_can_resume[embed]
FAILED tests/prep/test_pipeline.py::test_resume_retries_failed_rows_in_completed_shard[True]
FAILED tests/prep/test_pipeline.py::test_resume_retries_failed_rows_in_completed_shard[False]
4 failed, 24 passed, 1 warning in 10.28s
exit 1
```

Both disconnection cases failed because no exception was raised; both resume cases failed because the embedder received zero retry calls.

### GREEN

Command:

```text
cd backend && .venv/bin/python -m pytest tests/prep -q
```

Initial implementation: `28 passed, 1 warning in 10.47s` (exit 0).
After adding the retry-publication interruption regression:

```text
29 passed, 1 warning in 10.20s
exit 0
```

The warning is the existing Pydantic class-based configuration deprecation.

### Broader regression suite — executed once

Command:

```text
cd backend && .venv/bin/python -m pytest -q --ignore=tests/label/test_judge.py --ignore=tests/label/test_judge_resume.py
```

Output:

```text
FAILED tests/crawl/test_final_w5.py::test_finish_partial[blocked]
FAILED tests/crawl/test_final_w5.py::test_finish_partial[parse_error]
FAILED tests/test_integration_stage0_2.py::test_end_to_end_0_to_preprocess
FAILED tests/test_integration_stage0_2.py::test_no_api_keys_full_run
FAILED tests/test_integration_stage0_2.py::test_preprocess_reads_collection_chain
FAILED tests/test_integration_stage0_2.py::test_downstream_clustering_reads_compat_fields
FAILED tests/test_integration_stage0_2.py::test_missing_manifest_status_hides_path
FAILED tests/test_integration_stage0_2.py::test_default_crawl_config_reaches_preprocess
8 failed, 958 passed, 1 warning in 107.85s (0:01:47)
exit 1
```

Failure analysis: these existing crawl/integration tests use new-session preparation without configuring a fake embedder or Voyage credentials. Four assert done but now receive `{'status': 'error', 'error': 'Voyage API key is not configured'}`; the two finish-partial cases and collection-chain case expect compatibility documents that are no longer published after this error. The missing-manifest case expects a collection error, but embedder construction now raises the credential error first. These are consequences of the requested removal of offline zero-vector completion, not a green full-suite result. Their fixtures/expectations are outside this fix's ownership and were left unchanged; controller follow-up should explicitly configure a fake embedder for offline preprocessing tests (and address error precedence expectations as needed).

The full suite was not rerun. Complete captured output: `/tmp/t04-fix-round-1-full-pytest.log`.

Final `git diff --check`: exit 0, no output. Focused result remains **29 passed**; broader result remains **958 passed / 8 failed**. No commits were made.

## Fix round 2

### Changes

- Preserved the uncommitted fix-round-1 vector retry/recovery implementation and tests. Split compatibility export from final session publication: all document/token parts and `preprocessed/{sid}/{timestamp}.jsonl` now precede embedding, using the existing monkeypatchable `app.services.preprocessing.save_jsonl` connection.
- On constructor-time disconnection, retain only the configured provider identity for the stable prepKey and defer `EmbedderUnconnected` until compatibility output is durable. No fallback embedder or zero vectors are produced. The failed manifest remains retryable; no done session state is published. Collection errors now take precedence over missing credentials.
- Attach preparation counts to the propagated disconnection exception. Only the legacy `preprocess_data` service catches it and reports `status: done`, `embedding: unconnected`, and original/filtered counts. `/prep` API and worker behavior remain unchanged (`failed` / `embedder_unconnected`); `backend/app/routers/prep.py` was not edited.
- Same-key reconnection still computes nonzero vectors. Completed-result caching, vector-shard resume, failed-row retries, and interrupted retry publication remain covered by the retained fix-round-1 tests.
- This supersedes the fix-round-1 recommendation to change offline integration fixtures: the eight reported regressions are fixed in implementation, without editing those tests.
- Only the three owned files and this report were touched. No network access, git write commands, or commits.

### Covering tests and RED

Added `test_unconnected_exports_before_embedding`, parameterized over direct pipeline / legacy service and constructor-time / embedding-time disconnection (four cases). Two vector work shards verify complete docs and tokens exist at compatibility export, export occurs before embedding, compatibility fields/file are retained, no vectors or done state appear, and the legacy service finishes with the required embedding marker and counts.

```text
cd backend && .venv/bin/python -m pytest tests/prep/test_pipeline.py -k unconnected_exports_before_embedding -q
4 failed, 21 deselected, 1 warning in 1.96s
exit 1
```

Expected RED: constructor-time disconnection exported nothing and left the service in error; embedding-time cases reached compatibility export only after vectors had already been written. A preceding test-setup command used a duplicated `backend/` path and added no tests (`21 deselected`, exit 5); the corrected command above is the actual RED run before implementation.

### GREEN — required focused regression run

```text
cd backend && .venv/bin/python -m pytest tests/prep tests/test_integration_stage0_2.py tests/crawl/test_final_w5.py -q
81 passed, 2 warnings in 14.91s
exit 0
```

All eight reported regressions, the four new cases, the same-prepKey reconnect test, and existing prep/API coverage pass. Warnings concern the existing Pydantic configuration deprecation and joblib physical-core detection.

### GREEN — required broader suite, executed once

```text
cd backend && .venv/bin/python -m pytest -q --ignore=tests/label/test_judge.py --ignore=tests/label/test_judge_resume.py
970 passed, 2 warnings in 108.65s (0:01:48)
exit 0
```

Zero failures. The two warnings are the same existing Pydantic/joblib warnings noted above. `git diff --check` also passed (exit 0, no output). No commits were made.
