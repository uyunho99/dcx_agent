# T08 implementation report

## Implementation

Implemented the version-independent judgment cache and registered the `judge` worker while preserving `prep` registration. No calibration-first ordering was implemented (D-145). No network commands, git writes, or commits were performed.

- `VoteCache(root)` creates `votes.sqlite` with the specified `votes(doc_id, payload_json, status, attempts, last_error, run_id, at)` columns. A separate owners table records lease owner PIDs. Atomic `BEGIN IMMEDIATE` leases exclude live owners; dead owner leases are recovered. Seeds are idempotent; each successful vote commits immediately. Terminal rows are not overwritten by reseeding. Pending mutations are guarded by lease ownership. Failure counts persist across worker restarts; the third failed attempt marks the document `bad`.
- Cache paths are `data/judge/{sid}/{prepKey}/{labeler}/{qver}-{ctxKey}/votes.sqlite`. `ctxKey` is the first eight SHA-256 hex characters of concatenated one-liner, raw question file text, and configured model/backend identity. For Codex, the configured profile identifies its model configuration. No version appears in the cache path.
- Worker reads the requested version's `session.json`, `prep.derivedRef`, `projectContext.oneLiner`, and sorted prepared document JSONL shards under `derived/{sid}/{collectionId}/{prepKey}/docs/`. It rejects absent document folders and duplicate document IDs.
- Jev calls use the existing `JevClient` with keyword-only `idempotency_key=f"{doc_id}:{qver}-{ctx_key}"` and existing shared per-key limiter. Jev commits one document at a time, with cooperative worker checkpoints every 50 documents. A missing/invalid connection stops with a safe reason; insufficient credit releases pending leases and pauses.
- GPT uses `gpt.judge_batch(..., sid=..., ctx_key=..., qver=...)`, retaining valid peers and retrying missing documents only. Every member of an unusable batch accrues a failed attempt, including `LabelerPaused` failures. The three-failure limit persists across pauses/restarts and bounds poisoned run-manifest failures.
- Pauses use the existing work database action and blocking `Context.heartbeat`, preventing `execute()` from erroneously marking a paused run done. Pending leases are released before pausing and on exit. Another live version's leases are awaited rather than stolen.
- Status detail includes counts, progress, cache reference, estimated remaining seconds, estimated total Jev request tokens, and the exact context-change message `판정 맥락이 바뀌어 다시 판정합니다`. Jev request tokens use the sum of `ceil(len(compact request JSON)/4)`; its ETA uses configured per-key rate and key count. GPT ETA uses observed successful throughput within the last ten minutes and is unknown until sufficient observations exist.

## Exact files created/modified by this task

Created:
- `backend/app/label/votes.py`
- `backend/app/label/judge.py`
- `backend/tests/label/test_judge.py`
- `backend/tests/label/test_judge_resume.py`
- `.superpowers/sdd/03-plan/task-T08-report.md`

Modified:
- `backend/app/work/worker.py` — only lazy `judge` handler and KINDS registration.

Parallel modifications to `backend/app/prep/pipeline.py` and `backend/tests/prep/test_pipeline.py` were observed and left untouched.

## TDD evidence

### Initial RED, before implementation

Command:
```text
cd backend && .venv/bin/python -m pytest tests/label/test_judge.py tests/label/test_judge_resume.py -q
```
Output:
```text
EEEEEEEEEEFF [100%]
2 failed, 1 warning, 10 errors in 0.20s
```
Confirmed reasons: `ImportError: cannot import name 'judge' from 'app.label'` and `ModuleNotFoundError: No module named 'app.label.votes'`. Tests were created before either module. All required test names from the brief were included; the withdrawn calibration test was omitted.

### First GREEN

Command:
```text
cd backend && .venv/bin/python -m pytest tests/label -q
```
Output:
```text
105 passed, 1 warning in 1.22s
```

### Self-review RED and refactor

Added real Context pause/resume, status estimate publication, disconnected Jev stop behavior, and model/backend identity coverage. Made fake Context snapshot status detail as real serialization does, so subsequent dict mutations cannot hide missing publication.

Command:
```text
cd backend && .venv/bin/python -m pytest tests/label/test_judge.py -q
```
Output:
```text
FAILED test_worker_publishes_estimate
FAILED test_unconnected_stops_without_bad_documents
2 failed, 12 passed, 1 warning in 0.86s
```
Confirmed reasons: estimates were calculated after heartbeat without publication; disconnected Jev was paused instead of stopped. Fixed both. Strengthened SIGKILL coverage to invoke the actual judgment worker in a subprocess, kill immediately after the 40th durable commit, restart with a new run ID, and verify exactly 100 total unique fake Jev calls. Strengthened version-reuse coverage for both labelers, including unchanged fake Codex invocation logs.

### Final focused GREEN

Command:
```text
cd backend && .venv/bin/python -m pytest tests/label -q
```
Output:
```text
110 passed, 1 warning in 1.68s
```
The warning is the existing Pydantic class-based configuration deprecation in `app/config.py`.

## Full-suite result

Ran the requested full suite exactly once:
```text
cd backend && .venv/bin/python -m pytest -q --ignore=tests/prep/test_pipeline.py
```
Output:
```text
8 failed, 954 passed, 1 warning in 106.07s (0:01:46)
```

Failures outside T08:
- `tests/crawl/test_final_w5.py::test_finish_partial[blocked]`
- `tests/crawl/test_final_w5.py::test_finish_partial[parse_error]`
- `tests/test_integration_stage0_2.py::test_end_to_end_0_to_preprocess`
- `tests/test_integration_stage0_2.py::test_no_api_keys_full_run`
- `tests/test_integration_stage0_2.py::test_preprocess_reads_collection_chain`
- `tests/test_integration_stage0_2.py::test_downstream_clustering_reads_compat_fields`
- `tests/test_integration_stage0_2.py::test_missing_manifest_status_hides_path`
- `tests/test_integration_stage0_2.py::test_default_crawl_config_reaches_preprocess`

Five failures explicitly return `Voyage API key is not configured`; the two finish-partial cases observe no calls to the legacy `save_jsonl` hook, and collection-chain coverage observes no compatibility documents. Read-only inspection confirms schemaVersion 2 preprocessing delegates to `app.prep.pipeline.run_prep`, with default Voyage embedder selection. These failing paths do not invoke the new judgment worker. They concern preprocessing/integration expectations outside T08 ownership, including the ongoing parallel T04 changes; no baseline rerun or full-suite repetition was performed. No T08 label tests failed in the full suite. The controller should resolve these integration failures with the preprocessing task owner.


## Self-review and concerns

- Verified owned changes, clean `git diff --check`, prep registry preservation, per-document durability, lease exclusion/recovery, context isolation, both-labeler version reuse, offline fake providers, fake-clock rate limiting, partial GPT salvage, bounded failures, and real pause/resume lifecycle.
- The no-duplicate test covers a crash after a committed response. A crash between an external response and the SQLite commit can repeat the HTTP request; stable idempotency keys let the provider deduplicate that request. Local SQLite alone cannot make remote calls exactly once.
- Codex exposes a profile setting rather than a dedicated label model setting. Changing model configuration inside an unchanged external Codex profile is not observable to this cache key; change the profile identity when changing that model. Similarly, provider changes behind an unchanged model alias require a pinned/new model identity for cache invalidation.
- Prepared documents are loaded into memory once, matching the current preparation reader approach. Very large corpora may warrant a later indexed document reader; per-document work-status transactions are avoided.
- Context-change UI text is exposed through worker status detail; rendering the overview is outside the owned T08 backend files.
- Jev token estimates represent total requests for the input corpus, not a billing quote or a count of future retry traffic. Pause/resume latency for Jev is bounded by a 50-document checkpoint, plus provider retry delays.

## Fix round 1

Addressed both Important review findings without network access, git writes, or commits. T09's store.py, merge.py, and test_merge.py were not modified.

### Changes

- Added the backward-compatible `JevError.transient` attribute (default false). Transport exceptions and exhausted HTTP 429/all 5xx retries set it true while preserving existing safe messages and `code='bad'` for other callers. HTTP retries retain stable idempotency keys.
- The judge worker releases all outstanding leases on transient failures without consuming document attempts, ends the current batch, and backs off exponentially (1, 2, 4, 8 seconds; capped at 30 seconds). Five consecutive failures pause with `Jev 연결이 불안정해 판정을 멈췄습니다`. A successful response or non-transient document fault resets the streak; resuming a pause starts a fresh streak.
- Leases now order by `(attempts, doc_id)`. HTTP 422 and invalid/missing votes still consume document attempts and become bad after three failures.
- Added `LabelerPaused.usage_limit` (default false), set when Codex quota detection yields the usage-limit message. Only usage-limit pauses release without consuming attempts. Other paused causes retain bounded attempt accounting.
- Raised fake-Codex timeouts in test_judge.py/test_gpt.py and the real Context pause/resume poll/join deadlines from 5 to 30 seconds, preserving assertions.

Changed implementation files: backend/app/label/{judge,votes,jev,gpt}.py. Changed test files: backend/tests/label/{test_judge,test_judge_resume,test_jev,test_gpt}.py. This report was appended.

### TDD RED → GREEN

Added regression tests before implementation for a 100-document transport outage, repeated real fake-Codex quota pauses, lease fairness, transient error classification, and the quota flag.

Command (RED and focused GREEN):
```text
cd backend && .venv/bin/python -m pytest tests/label/test_judge.py tests/label/test_judge_resume.py tests/label/test_jev.py tests/label/test_gpt.py -q
```
RED output: `10 failed, 95 passed, 1 warning in 1.84s`.
The outage made 300 requests instead of pausing after five; the quota pause persisted attempts=1 instead of 0. Remaining failures exposed missing error attributes, missing 5xx retries, and doc_id-only ordering.

Focused GREEN output after implementation: `105 passed, 1 warning in 1.69s`.

Added recovery coverage proving that successful votes reset the consecutive failure count, plus explicit 422/missing-answer tests proving per-document failures still reach three attempts. Existing tests preserve bounded non-quota GPT failures, pause/resume, version reuse, and crash recovery assertions.

### Required three consecutive runs

Executed this exact command three times sequentially, with no code changes between runs:
```text
cd backend && .venv/bin/python -m pytest tests/label -q --ignore=tests/label/test_merge.py
```

1. `119 passed, 1 warning in 1.80s`
2. `119 passed, 1 warning in 1.84s`
3. `119 passed, 1 warning in 1.83s`

All exited 0. The warning is the existing Pydantic class-based configuration deprecation in app/config.py. `git diff --check` exited 0 with no output.

## Fix round 2

Updated `backend/tests/label/test_judge_resume.py` to derive the backend directory with `Path(__file__).resolve().parents[2]` and pass it as `cwd` to both crash/restart subprocess calls. This follows the explicit backend working-directory pattern in `tests/crawl/test_resume.py` and makes child imports independent of where pytest starts.

Scanned `backend/tests/label/` and `backend/tests/prep/` for other subprocess and working-directory-relative paths. No other fixes were needed: fixture/source/fake-executable paths derive from `__file__`, test data paths use temporary directories, and prep API workers launch through the runner's explicit backend `cwd`. T09's `store.py`, `merge.py`, and `test_merge.py` were left untouched. No production code, network access, git writes, or commits were involved.

Repository-root command:
```text
backend/.venv/bin/python -m pytest backend/tests/label backend/tests/prep -q --ignore=backend/tests/label/test_merge.py
```
Output:
```text
152 passed, 1 warning in 12.06s
```

Backend-directory command:
```text
cd backend && .venv/bin/python -m pytest tests/label tests/prep -q --ignore=tests/label/test_merge.py
```
Output:
```text
152 passed, 1 warning in 12.32s
```

Both commands exited 0. Each warning is the existing Pydantic class-based configuration deprecation in `app/config.py`. `git diff --check` exited 0 with no output.
