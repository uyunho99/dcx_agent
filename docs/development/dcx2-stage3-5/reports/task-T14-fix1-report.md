# T14 fix round 1 report

## Scope and outcome

Implemented all five requested fixes from `task-T14-fix1.md`. Read the original brief and review findings before changing code.

Files changed by this task:

- `backend/app/services/personas.py`
- `backend/app/known/filter.py`
- `backend/app/known/store.py`
- `backend/tests/known/test_known.py`
- `.superpowers/sdd/03-plan/task-T14-fix1-report.md`

No router change was needed: handling invalid export references in the shared search function fixes `/search` as well as its other callers. No packages installed and no commit created. Existing concurrent changes in sessions, context/versions, frontend, and other tests were left untouched.

## Changes

1. **Persona fallback evidence:** Empty retrieval results with `no_vectors`, `no_labels`, or `embedder_unconnected` use the cluster's first 20 raw documents, removing Known Insight doc IDs. `all_known` still suppresses fallback. A real legacy session without `derivedRef` is covered.
2. **Search lock duration and scans:** Load session data and capture the active version directory under the session lock; release it before metadata reads, embedding, and vector scans. Pass the captured directory to label and Known vector readers so later reads do not resolve a different active version. Remove the separate `valid` shard scan; `cosine_topk` receives the relevant document IDs and handles failed/zero/nonfinite vectors. Missing preparation or an empty vector store returns `no_vectors`; empty candidate results also preserve `no_vectors` for unusable rows. All four reason strings remain supported.
3. **Initialization embedding batch:** Collect statements missing vectors and embed them in one call. Append valid rows, then flush/fsync before publishing row pointers with the session update. Existing vectors are not re-embedded; provider failures retain the statements. Single-item add/PATCH use the same helper.
4. **Invalid export references:** Catch `StoreError` from relevant-document lookup and return `no_labels` with correctly sized empty result lists. Tests cover missing exports, the wrong filename, and another session's export path, including HTTP 200 from `/search`.
5. **Empty persona queries:** Trim queries and omit empty queries from the single search batch. Preserve cluster-to-result mapping and use filtered raw evidence for clusters without queries. If every query is empty, skip search entirely.

## TDD and verification

Tests were added before production edits.

- RED: `backend/.venv/bin/python -m pytest backend/tests/known/test_known.py -q` — **10 failed, 21 passed**. Failures reproduced missing fallback (three reasons), empty-query handling (mixed/all-empty), lock retention, invalid exports (three paths), and per-statement initialization calls. The `all_known` control stayed green.
- GREEN: same targeted command — **31 passed**, 2 warnings, 2.11 seconds.
- New lock regression uses a non-blocking exclusive `flock` on the actual session lock during metadata reads, embedding, and vector iteration. It also asserts exactly one shard-scan invocation.
- Initialization regression checks one batched call, deduplication of copied statements, persisted vector row alignment, and no extra call on repeat initialization.
- `git diff --check` passed after implementation.
- Full required suite from repository root: `backend/.venv/bin/python -m pytest backend/tests -q` — **1168 passed**, 2 warnings, 117.87 seconds. No exclusions.
- Both runs reported the existing Pydantic class-based configuration deprecation and joblib physical-core detection warning; neither affected test results.

## Remaining scope and limitations

The parked legacy `createdAt` churn and legacy CRUD error message were not changed. Search still loads relevant-document metadata for each request, but does so outside the session lock; no large-corpus benchmark was performed. Initialization remains serialized under its existing session lock, now with one embedding call for all missing statement vectors. The session snapshot pins data and version paths; it is not a transaction across every artifact file.
