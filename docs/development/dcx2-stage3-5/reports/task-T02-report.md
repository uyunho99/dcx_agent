# T02 implementation report

Status: DONE

## Implemented

- Added `Embedder` protocol, deterministic SHA-256-seeded normal-distribution `FakeEmbedder` with L2 normalization, `VoyageEmbedder`, `EmbedderUnconnected`, and settings-based factory. Empty results retain `(0, dim)` float32 shape. Missing/blank keys and the existing `x` placeholder report unconnected.
- Updated the shared Voyage service to use `settings.embed_model` (default `voyage-4`) and `output_dimension=settings.embed_dim` (default 1024), retaining 128-input batches, 2,000-character truncation, and blank-input substitution. Failed batches and invalid/missing response rows become zero vectors. Provider exception payloads are no longer printed, preventing credential leakage.
- Added `VectorStore(root)` where root is the prepKey directory. Writes split at 10,000 rows into one-based `vectors/shard-{n:05d}.f16` files. `vectors/ids.jsonl` records document ID, shard number, row, and failure flag. Failed rows are physically zeroed. Duplicate IDs, dimension mismatches, invalid shapes, nonfinite vectors, and float16 overflow are rejected.
- Shard bytes and directory entries are fsynced before index publication. Logical index appends use an fsynced temporary snapshot and atomic replacement, so an interrupted publication preserves the previous index. Orphan shard files remain unreferenced and are skipped when assigning future shard numbers.
- Added ordered `get` (including repeated requested IDs and omission of missing IDs), float32 shard iteration with boolean failure masks, count, and completed-shard count. Dimensions are inferred from committed shard files on reopening.
- Added process-level bounded caches for parsed indexes and read-only NumPy memmaps, keyed by resolved paths and file signatures. Separate store instances reuse unchanged shard mappings; appended index revisions are refreshed. `get` resolves each selected shard mapping once rather than statting it for every selected row.
- Added batched normalized cosine matrix multiplication per shard, global top-k merging, allow/exclude filtering, zero/failed-vector exclusion, stable tie ordering, and empty results for zero queries/empty stores.

## Exact files created or modified

Controller commit allowlist (no T03 files):

1. CREATED `backend/app/vectors/__init__.py`
2. CREATED `backend/app/vectors/embedder.py`
3. CREATED `backend/app/vectors/store.py`
4. CREATED `backend/app/vectors/search.py`
5. MODIFIED `backend/app/services/voyage.py`
6. CREATED `backend/tests/vectors/__init__.py`
7. CREATED `backend/tests/vectors/test_embedder.py`
8. CREATED `backend/tests/vectors/test_store.py`
9. CREATED `backend/tests/vectors/test_search.py`
10. CREATED `.superpowers/sdd/03-plan/task-T02-report.md` (this explicitly requested report)

No network access, dependency installation, or git write commands were used. Parallel T03 changes were preserved untouched.

## TDD evidence

### Initial RED

Command:

```sh
cd backend && .venv/bin/python -m pytest tests/vectors -q
```

The five required named tests were written before implementation, alongside coverage for connection state, API failure handling, empty stores, append/reopen behavior, input validation, and memmap reuse.

Failing excerpt:

```text
ERROR tests/vectors/test_embedder.py
ERROR tests/vectors/test_search.py
ERROR tests/vectors/test_store.py
E   ModuleNotFoundError: No module named 'app.vectors'
1 warning, 3 errors in 1.16s
```

Expected because the vectors package had not yet been implemented.

### Initial GREEN

Same command:

```text
12 passed, 1 warning in 1.44s
```

### Self-review RED/GREEN additions

`cd backend && .venv/bin/python -m pytest tests/vectors/test_embedder.py::test_voyage_invalid_response_rows_are_zero -q`

```text
E ValueError: setting an array element with a sequence.
1 failed, 1 warning in 0.88s
```

Expected: malformed and missing response rows originally reached NumPy without validation. Added per-row validation preserving valid embeddings and filling invalid/missing rows with zeros.

`cd backend && .venv/bin/python -m pytest tests/vectors/test_store.py::test_store_interrupted_index_publication_keeps_previous_shards -q`

```text
E Failed: DID NOT RAISE OSError
1 failed, 1 warning in 0.07s
```

Expected: the initial append implementation had no atomic index publication boundary. Added atomic replacement and tested interrupted publication, reopening, and subsequent successful retry.

Final focused command:

```sh
cd backend && .venv/bin/python -m pytest tests/vectors -q
```

```text
14 passed, 1 warning in 1.08s
```

## Full suite

Command: `cd backend && .venv/bin/python -m pytest -q`

The first invocation stopped during collection because the required `test_store.py` basename collided with `tests/context/test_store.py`. Added `backend/tests/vectors/__init__.py` to namespace the new tests, reran focused tests successfully, then reran the full suite.

Final full-suite result:

```text
855 passed, 2 warnings in 98.64s (0:01:38)
```

No failures in T03-owned files or elsewhere. Warnings were the existing Pydantic class-config deprecation and joblib falling back to logical CPU count.

## Self-review and concerns

- Required constants and interface shapes checked against the brief and design sections 2.2 and 3.3. Brief's `get -> (ids, vectors)` signature takes precedence over the older design shorthand.
- 25,000 rows at 1024 dimensions round-trip through three float16 shards with error below 1e-3. Requested order and duplicate requests survive reopening.
- Mock-only Voyage tests verify exact default request model/dimension, truncation, batch boundaries, failures, missing rows, and secret-free output.
- Cache reuse is tested across store instances; zero-vector and failure-mask handling are tested independently of query filters.
- `git diff --check` passes.
- No blocking concerns. The store assumes one writer per prepKey; there is no multi-writer locking. Cached entries are bounded (32 index revisions and 256 mappings), so evicted entries can be reopened. Atomic index publication copies the existing index per committed shard. Million-document latency, cache memory at that scale, and live Voyage integration were not benchmarked or exercised in this offline task. The existing Pydantic class-config deprecation warning is outside T02 ownership.
