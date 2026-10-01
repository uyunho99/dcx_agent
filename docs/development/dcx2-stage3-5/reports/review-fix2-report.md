# DCX2 stage 3–5 review-fix2 report

Date: 2026-09-30

## Requirements and scope

Read `.superpowers/sdd/03-plan/review-fix2.md` first and reviewed the findings in `docs/development/dcx2-stage3-5/reports/review-fix1-rereview.md`. Implemented the three items selected by the fix brief: cached trainable counts, README table continuity, and the unknown queue-reason fallback. Other observations in the rereview were outside this follow-up's scope.

No packages were installed and no commit was created. The pre-existing untracked rereview file was left unchanged.

## Changes

### 1. Cache the trainable count

Changed `backend/app/model/dataset.py`. The existing call in `backend/app/label/overview.py` already uses `trainable_count`, so no caller/API change was necessary.

- Store one cached key/count and a durable label revision in each version's `labels.sqlite` (`trainable_cache`). Existing databases acquire the table and triggers lazily.
- Key the count on the cache format version, shared training predicate, `derivedRef`, prepared artifact paths/stamps, and label revision.
- Artifact stamps cover the prep manifest, document directory and JSONL files, vector index, and vector shards. They include size, nanosecond modification/change times, and inode. This catches same-size vector rewrites as well as changed references and index publications without reading document contents or loading vectors on a cache hit.
- SQLite triggers increment the revision for inserts, updates, and deletes in both `final` and `human`. This avoids the missed updates/deletes possible with a max-rowid key and avoids comparing `PRAGMA data_version` across short-lived connections. Unrelated overview bookkeeping does not change this revision.
- Preserve the prior selection: human labels or accepted agreed labels, intersected with prepared document IDs and finite, nonzero vectors. The same `TRAINING_WHERE` continues to serve the training worker.
- Read selected IDs and their revision together, then perform a cold scan outside the labels write transaction. Persist the result only if prepared stamps still match and the label revision has not changed. A concurrent mutation therefore cannot mark an old count current.
- Cache zero counts too. No process-local corpus/vector cache is introduced.

Added `backend/tests/test_review_fix2.py` with 11 cases covering unchanged polling, real HTTP human submission, final-row update/delete, human insertion, document/manifest/vector/index/reference changes, an empty selection followed by new labels, and a label mutation during a scan. The tests monkeypatch `infer.documents` and `VectorStore.iter_shards` to verify call counts across separate overview requests and database connections.

### 2. Repair the README settings table

Removed the single blank line between the `CORS_ORIGINS` and `STORAGE` rows in `README.md`. All settings rows now remain contiguous beneath the existing table header. Verified the exact one-line deletion in the diff.

### 3. Unknown queue-reason fallback

Changed `frontend/src/components/label/queueView.ts` to return `기타` when a nonempty reason is not found in the label mapping. Existing known labels and absent-reason audit/reissue labels remain intact.

Added a Vitest regression in `frontend/src/components/label/queueView.test.ts` for an unknown reason in both default and audit modes.

## TDD evidence

Tests were added and run before production changes:

1. `backend/.venv/bin/python -m pytest backend/tests/test_review_fix2.py -q`: **9 failed**. Each failure showed the second unchanged overview had called document parsing and vector iteration twice instead of once.
2. `npm --prefix frontend test -- --run src/components/label/queueView.test.ts`: **1 failed, 2 passed**. The new test received `undefined` instead of `기타`.

After implementation:

1. `backend/.venv/bin/python -m pytest backend/tests/test_review_fix2.py backend/tests/test_review_fix1.py -q`: **36 passed**, including the existing 40-usable-human-label training parity regression.
2. Focused queue Vitest: **3 passed**.
3. Added the empty-selection and concurrent-label-change cases before running the full suites.

## Full validation

- `backend/.venv/bin/python -m pytest backend/tests -q`: **1,255 passed, 2 warnings in 121.50 seconds**, exit 0.
- `npm --prefix frontend test -- --run`: **222 passed across 40 files**, exit 0.
- `git diff --check`: passed.

Backend warnings concerned Pydantic class-based configuration deprecation and joblib's fallback from physical to logical CPU counts. Frontend output included Node's `module.register()` deprecation warning. No test failures remained.

## Operational notes

Warm count lookups perform file metadata checks and small SQLite operations; their cost scales with artifact file count, not document/vector contents. Cold cache misses retain the existing full scan and allocation behavior. Simultaneous cold requests may both scan. A request whose labels change during its scan can return its earlier selection count once, but cannot persist that count against the newer label revision; the next poll recomputes. These are count-cache behavior limits, not changes to training selection.

The requested report lives under the repository-ignored `.superpowers` directory and was written directly at the requested path.

## Status

Complete: all three requested fixes implemented, failing-test-first evidence recorded, and both required full suites passed. No commits or package installations.
