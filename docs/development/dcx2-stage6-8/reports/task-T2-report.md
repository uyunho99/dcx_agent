# Task T2 report

- status: implemented; targeted tests GREEN; full-suite verification has three independently reproducible failures outside T2
- executor: codex
- worktree: `/Users/persona1/Desktop/dcx_agent-stage6-8`
- branch: `feature/dcx2-stage6-8`

## Files changed

- `backend/app/segment/__init__.py`: package foundation.
- `backend/app/segment/params.py`: all 34 constants from the task brief, with exact values.
- `backend/app/segment/store.py`: version-local SQLite schema, transactional layer replacement and confirmation, paginated document queries, natural ID ordering, request notes, and current-run metadata.
- `backend/app/segment/inputs.py`: version-specific export/preparation loading, channel and original-document joins, float16 normalized vectors, exclusions/reporting, and shared noun cache.
- `backend/requirements.txt`: added `gensim>=4.4` and `networkx>=3.3`.
- `backend/tests/segment/test_store.py`: four persistence tests.
- `backend/tests/segment/test_inputs.py`: eight input/cache tests.
- `.superpowers/sdd/03-plan/task-T2-report.md`: this requested report.

No other checkout was modified. No git add or commit was run.

## RED evidence

Tests were written before creating `app/segment`.

Command (all test commands used fake backends and the suite's external-network guard):

```sh
EMBED_BACKEND=fake LLM_BACKEND=fake backend/.venv/bin/python -m pytest backend/tests/segment/test_store.py backend/tests/segment/test_inputs.py -q
```

Initial result: exit 2; two collection errors in 2.13s. Both test modules failed with `ModuleNotFoundError: No module named 'app.segment'`.

## GREEN evidence

- Minimal implementation: **8 passed**, one existing Pydantic warning, 2.33s.
- Added cache interruption/corruption recovery, noun-only reuse, and empty-input checks: **12 passed**, one warning, 2.87s.
- Refactored the document join to explicitly separate export labels from preparation text/channel metadata: **12 passed**, one warning, 1.89s.
- Parsed the brief's constant assignments and `params.py` with Python AST: all **34** names and literal values match exactly.
- `git diff --check`: clean.

Coverage includes:

- All seven tables, version isolation, JSON fields, float32 centroid BLOB round-trip, docs filtering/pagination, and natural `CL0`, `CL2`, `CL10` ordering.
- Atomic result replacement, last-write-wins confirmations, retained drafts, and context confirmation rollback after an injected SQL failure on the second update.
- Rejection of a context outside the requested Persona, without leaving earlier items confirmed.
- Run ID persistence across reopened stores and isolation from another version.
- The synthetic fixture's two zero-vector exclusions and one zero-token exclusion, float16 output with normalized vectors, original text truncation counts, and channel totals.
- Derived channel, author, comments and date join; judging origin retained as `judge_source`; stage-five probabilities/labels preserved.
- Noun-only preparation reuse without Kiwi; mixed-POS fallback extraction; second-load and new-version cache hits with zero Kiwi calls.
- Cache shard publication through `store.atomic_write`; manifest-last completion; rebuilding unmarked partial files, missing/damaged shards, and a failed manifest publication.
- Empty relevant exports and actionable errors for absent token shards.

## Full-suite result

Executed the full suite **once**, as requested:

```sh
EMBED_BACKEND=fake LLM_BACKEND=fake backend/.venv/bin/python -m pytest backend/tests -q
```

Result: **3 failed, 1491 passed, 1 deselected, 2 warnings in 144.67s**; exit 1.

Failures:

1. `backend/tests/crawl/test_final_w5.py::test_finish_partial[blocked]`: expected saved IDs `['collected']`, received `['collected', 'collected']` at line 62.
2. `backend/tests/crawl/test_final_w5.py::test_finish_partial[parse_error]`: identical duplicate-save assertion.
3. `backend/tests/llm/test_registry.py::test_default_backend_is_openai`: expects `settings.llm_backend == 'openai_api'`, but the explicitly required environment sets it to `fake`.

To check independence from T2 test execution, ran only the failing existing tests in a fresh process, retaining the required fake backends:

```sh
EMBED_BACKEND=fake LLM_BACKEND=fake backend/.venv/bin/python -m pytest backend/tests/crawl/test_final_w5.py::test_finish_partial backend/tests/llm/test_registry.py::test_default_backend_is_openai -q
```

Result: **the same 3 failed**, one warning, 2.70s. No segment tests were collected in this isolated check. The failing source files were not modified.

Raw logs: `/tmp/dcx-task-T2-full-suite.log` and `/tmp/dcx-task-T2-failure-check.log`.

Warnings concern the existing Pydantic class-based configuration and joblib's physical-core detection.

## Self-review

- Storage resolves through `version_dir(sid, version)/segment/segment.sqlite`; loading reads the requested version snapshot rather than whichever version is active.
- SQL mutation scopes use `BEGIN IMMEDIATE`, commit on success, rollback on any exception, and close connections. Both regular confirmation and bulk confirmation preserve draft columns.
- Store row interfaces use schema snake_case names. JSON columns accept serialized JSON or Python values; reads decode them and remove `_json`, except `theta_json`, which retains its name to distinguish the full distribution from scalar `theta`. Centroids return float32 arrays.
- `write_layers` replaces all six result tables atomically; omitted tables become empty. `meta.run` is managed separately with `get_run`/`set_run`, for T9/T10.
- Layer names are `clusters`, `personas`, `contexts`. Split/merge request notes use `clusters.requests_json`, the location specified by the schema. Writable-version validation, API payload validation, upstream confirmation locks, and stale-run rejection remain responsibilities of the later controller/API tasks.
- Noun cache covers all prepared documents, so another version may change its relevant subset while reusing the same cache. The shared session lock prevents concurrent builders from publishing competing generations. Cache completion is published only after durable shard writes.
- Stage-three tokens contain plain strings, not per-token POS annotations. When manifest `config.tokenPos` contains only `NN*` tags, existing tokens are reused; otherwise noun-only tokenization uses `('NNG', 'NNP')` and is cached.
- The retained vector matrix is float16. `VectorStore.get` and normalization operate in bounded 10,000-row float32 batches. No full float32 result matrix is retained.
- Truncation counts use the preparation embedding text layout: title, body, and comments separated by newlines, before its 2,000-character limit. Counts cover relevant rows before exclusions; channel counts cover retained rows. A row with both a missing/zero vector and empty tokens counts under zero-vector exclusion first.
- No targetScope, model calls, network requests, unrelated refactors, or changes to earlier-task fixtures were introduced.

## Concerns

- The required full-suite run is not green: the three failures above reproduce independently of the T2 tests. They are outside the owned files and were left unchanged.
- Million-document throughput and memory usage were not benchmarked in T2. Vector conversion is bounded, while prepared documents/tokens and the returned dictionaries are in memory as specified by the input contract.
- No blocking issue found in the implemented T2 contracts.

## Fix round 1

- Status: fixed both review findings. Only `backend/app/segment/inputs.py`, `backend/tests/segment/test_inputs.py`, and this appended report were edited. No git add/commit or subagents.
- `_nouns` now serializes cache readers/builders with `fcntl.flock(LOCK_EX)` on the persistent `root/nouns/.lock` file. Closing the file releases the lock on return or exception. It no longer acquires the shared session lock. Shards still use atomic writes and the completion manifest is still published last.
- The cache still covers **all prepared documents**, keyed by the preparation root/prepKey and shared across versions. It is not narrowed to the relevant export.
- `report['truncated']` now counts only final target documents, after zero-vector and no-token exclusions.
- These changes supersede the earlier self-review statements about the shared session lock and pre-exclusion truncation counts.

### Covering tests and RED evidence

Added `test_load_input_does_not_take_session_lock` and `test_truncated_counts_only_final_target_docs` before changing production code.

```sh
backend/.venv/bin/python -m pytest backend/tests/segment/test_inputs.py -q -k 'does_not_take_session_lock or truncated_counts_only_final_target_docs'
```

Output: **2 failed, 8 deselected, 1 warning in 3.04s** (exit 1). The first failed at `store.locked(sid)` via the monkeypatched rejection; the second reported `5` truncated documents instead of `2`.

The lock regression uses the default mixed POS list, checks first-build and cache-hit paths without any session-lock acquisition, and was extended to select only two relevant documents while asserting Kiwi runs for all 16 prepared documents. A second version selects the larger export with zero additional Kiwi calls. The truncation regression makes both zero-vector documents and the no-token document long, alongside two retained long documents (body/comment), and expects only the latter two to count.

### GREEN and full-suite verification

```sh
backend/.venv/bin/python -m pytest backend/tests/segment -q
```

After the production fix: **24 passed, 1 warning in 5.03s**. Extending the version/subset regression initially used an invalid export path and produced **1 failed, 23 passed, 1 warning in 5.75s**. Corrected that test fixture to use `classified/{sid}/v2/gen-synth/relevant.jsonl`; final segment run: **24 passed, 1 warning in 5.46s** (exit 0).

Full suite executed **once**, with the exact requested command (stdout/stderr saved to `/tmp/dcx-task-T2-fix-round1-full-suite.log`):

```sh
backend/.venv/bin/python -m pytest backend/tests -q
```

Output: **1 failed, 1495 passed, 1 deselected, 2 warnings in 144.52s** (exit 1). The run was started prematurely after the test-extension failure and had already imported its invalid export-path fixture before the correction. Its only failure was `backend/tests/segment/test_inputs.py::test_load_input_does_not_take_session_lock`, raising `StoreError` from `read_export` for that invalid path. This is a test-authoring/timing error, not a sandbox/environment failure. No non-segment tests failed. The final corrected test passed in the segment run above and was rerun individually after the full-suite result:

```sh
backend/.venv/bin/python -m pytest backend/tests/segment/test_inputs.py::test_load_input_does_not_take_session_lock -q
```

Output: **1 passed, 1 warning** (exit 0). The full suite was not rerun, respecting the requested single run. Thus the final segment code/tests are green, but there is no fully green full-suite run of the final test revision.

`git diff --check`: clean. Existing warnings concern Pydantic class-based configuration and joblib physical-core detection. No remaining implementation concern identified within this fix's scope; full-suite verification has the timing limitation described above.
