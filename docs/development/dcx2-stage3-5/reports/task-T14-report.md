# T14 implementation report

## Status

Implementation is present and the targeted T14 tests pass. Full-suite acceptance is **not complete**: an existing, out-of-ownership stage-0–2 integration test expects the preprocessed-document fallback that controller ruling 2 expressly prohibits for new sessions. The final full-suite rerun produced 934 passed and 1 failed (the same contract conflict). No commit or other git write operation was performed. No network tools were used.

## Implementation

- Added the `KnownInsight` model with the exact wire keys `id`, `type`, `text`, `doc_id`, `from`, `createdAt`, and `vectorRow`. `read_known()` converts legacy strings to statement objects. `ProjectContext.knownInsights` remains `list[str]`, as design section 2.6 requires; compatibility belongs to the session reader, so `app/context/models.py` did not need modification.
- Added version-local CRUD behind the session lock, atomic session metadata updates, and append-only `known_vectors.f16`. Statements embed on addition; unchanged successfully embedded statements do not embed again. Changed statements append a new row. Failed/unconnected embeddings preserve the statement and expose `유사도 제외는 임베딩 연결 후 적용됩니다`; a later text PATCH can retry a missing vector. Document entries retrieve stage-three vectors without embedding calls.
- Added GET/POST/PATCH/DELETE `/known/{sid}` routes (item ID for PATCH/DELETE), validation, missing-item errors, and active-version write checks. API output uses “Known Insight.”
- Added exactly one initialization call (plus its local import) in `post_context`. It initializes stage-0 statements and copies only statements from other sessions with the same `bk`, reading each source session's active version and tagging copies `from=prev_session`. It deduplicates copied statements by exact text.
- Added `search_docs(sid, queries, top_k, novel=True) -> SearchResult`. `items` is an ordered list of result lists, one per query; `reason` describes a batch with no usable results. It uses the active session snapshot, the exact export file when referenced, otherwise accepted/audited final Core/Supporting rows including human-reviewed rows whose route is `escalated:human`.
- Local retrieval calls T02 `cosine_topk` with `top_k * 3` candidates per query, excludes zero/failed document vectors, then excludes Known Insight document IDs and candidates whose maximum Known Insight cosine is at least `settings.known_theta` (unchanged default `0.85`). `novel=False` disables only Known Insight filtering; the Core/Supporting restriction remains. Reasons implemented: `no_vectors`, `no_labels`, `all_known`, `embedder_unconnected`.
- Query embedding uses the preparation manifest's backend, falling back to preparation configuration and then settings; incompatible model/dimension metadata yields `embedder_unconnected`. Queries are passed as one list to the embedder; the existing Voyage adapter supplies 128-item batching, 2,000-character clipping, `voyage-4`, and 1024 dimensions.
- Replaced both chat retrieval calls, search retrieval, and persona retrieval. All request schemas accept `novel=True`, including persona configuration. Chat source items retain `doc_id`, and chat/search expose the reason. Persona queries are submitted together and empty filtered results do not fall back to excluded raw documents.
- New-session clustering reads only the exact `training.exportRef` JSONL file and joins its Core/Supporting IDs to stage-three vectors. It never invokes the embedding provider. A missing export produces exactly `5단계 결과가 없습니다`. Legacy sessions retain the prior path. Invalid/zero vectors are omitted and empty usable input yields a controlled error. Cluster count is bounded by usable document count.
- Export reading stays within the current session's classified tree and never invokes the S3 compatibility loader, avoiding the adjacent `all.jsonl` duplicate-input bug. An inherited exportRef from an earlier version is supported because version snapshots intentionally preserve references.
- Stage 6.5 immediately completes with `3단계 벡터 사용`; it performs no upload or embedding. Legacy sessions without stage-three vectors return `no_vectors` from search.
- Deleted the Pinecone service, its requirement line, and its Settings field. A search of existing tests found no pre-existing `pinecone_svc` references requiring migration.

## Exact implementation/test files

Created:

1. `backend/app/known/__init__.py`
2. `backend/app/known/models.py`
3. `backend/app/known/store.py`
4. `backend/app/known/filter.py`
5. `backend/app/routers/known.py`
6. `backend/tests/known/test_known.py`

Modified:

7. `backend/app/config.py` — Pinecone field removal only.
8. `backend/app/main.py` — Known Insight router import/include only.
9. `backend/app/models/schemas.py`
10. `backend/app/routers/chat.py`
11. `backend/app/routers/search.py`
12. `backend/app/routers/context.py` — one initialization call and its local import only.
13. `backend/app/services/clustering.py`
14. `backend/app/services/embedding.py`
15. `backend/app/services/personas.py`
16. `backend/requirements.txt` — Pinecone requirement removal only.

Deleted:

17. `backend/app/services/pinecone_svc.py`

Report/evidence artifacts, all under `.superpowers/sdd/03-plan/`:

- `task-T14-report.md`
- `task-T14-red.log`
- `task-T14-review-red.log`
- `task-T14-embedder-red.log`
- `task-T14-failure-red.log`
- `task-T14-export-red.log`
- `task-T14-green.log`
- `task-T14-suite.log`
- `task-T14-suite-final.log`

The other implementer's T11 changes under `app/label`, `routers/labeling_v2.py`, and `tests/label` were neither edited nor reverted. The out-of-scope integration test was not modified.

## TDD evidence

1. Wrote all eight brief-named tests before implementation:
   - `test_statement_and_doc_excluded`
   - `test_toggle_off_returns_all`
   - `test_theta_similarity_cut`
   - `test_search_legacy_session_reason`
   - `test_prev_session_statements_copied`
   - `test_clustering_reads_store_no_embed_calls`
   - `test_clustering_input_is_core_supporting_only`
   - `test_no_pinecone_import`
2. RED: root command `backend/.venv/bin/python -m pytest backend/tests/known -q` produced **5 failed, 3 errors** after correcting an initial fixture setup mistake. The three setup errors were imports of the not-yet-implemented Known Insight package. Other failures demonstrated missing copying/search, forbidden clustering embedding/fallback, and the remaining Settings field. Evidence: `task-T14-red.log`.
3. Minimum implementation GREEN: the same command produced **8 passed**.
4. Review tests exposed final human-label omission. The first review run also exposed an incorrect test assumption that a readonly version could be activated; the test was corrected to restore through the existing version-copy API. Evidence: `task-T14-review-red.log` (**2 failed, 14 passed**), followed by **16 passed**.
5. Additional RED: preparation backend override and retry of an unconnected statement (**2 failed, 16 passed**), followed by **18 passed**. Evidence: `task-T14-embedder-red.log`.
6. Additional RED: preserve a statement on provider failure (**1 failed**), followed by **19 passed**. Evidence: `task-T14-failure-red.log`.
7. Additional RED: inherited exact exportRef when restarting at stage 6 (**1 failed**), followed by **20 passed**. Evidence: `task-T14-export-red.log`.
8. Refactoring shares exact-file export reading and preparation resolution, keeps batch query/result alignment explicit, and preserves existing vector-store/search implementations unchanged.

## Validation

- Final targeted command from repository root: `backend/.venv/bin/python -m pytest backend/tests/known -q` — **20 passed, 2 warnings in 1.82s** (`task-T14-green.log`).
- Initial full command: `cd backend && .venv/bin/python -m pytest -q --ignore=tests/label` — **930 passed, 1 failed, 2 warnings in 111.66s** (`task-T14-suite.log`).
- Final full command: `cd backend && .venv/bin/python -m pytest -q --ignore=tests/label` — **934 passed, 1 failed, 2 warnings in 112.14s** (`task-T14-suite-final.log`). The only failure is the conflicting clustering compatibility test described below.
- `git diff --check` — clean.
- `rg -n 'pinecone|search_similar' backend/app backend/requirements.txt` — no matches.
- No frontend work or browser QA was attempted: the assigned scope is the backend T14 implementation; UI work is separately planned as T-D6.

## Self-review and concerns

### Unresolved full-suite contract conflict

`backend/tests/test_integration_stage0_2.py::test_downstream_clustering_reads_compat_fields` creates a fresh schemaVersion-2 session through `/context`, runs only the old preprocessing path, provides no `training.exportRef`, mocks the old embedding call, and expects successful clustering of all 200 preprocessed documents. T14 controller ruling 2 explicitly requires new sessions without an export to error with `5단계 결과가 없습니다`, never falling back to all preprocessed documents. The implementation returns that required error, so this old test fails.

Changing production behavior to satisfy the test would violate the controller ruling. Updating this test is outside the user's explicit file ownership (the only additional test-edit authorization was for existing tests referencing `pinecone_svc`, which this test does not). No question was asked, per instruction. The smallest scope-preserving choice was to retain the required behavior and report the conflict. To finish full-suite acceptance, the owner should update this test to prepare a real stage-five export and stage-three vectors, or explicitly construct a schemaVersion-less legacy session if its intent is legacy fallback compatibility. It should not be deleted.

### Decisions and practical limits

- `SearchResult.items` is nested by input query; single-query HTTP callers unwrap the first list. One `reason` describes the whole batch, so a partially empty batch retains per-query empty lists and no `all_known` reason when another query has results.
- Previous-session copying considers all other same-bk active sessions and deduplicates statements by exact text. Doc items never copy.
- Statement edits append vector rows; deletion leaves unused rows so existing pointers and version snapshots remain stable. Vector-file compaction is not part of T14.
- Unconnected/failed statements require a later text PATCH to retry; successful vectors are not recomputed during searches.
- Exact exportRef inheritance is allowed within a session's export tree; the referenced file is never replaced with a directory scan.
- Core/Supporting eligibility is enforced even when novelty filtering is off. Human-reviewed rows are included regardless of the historical `escalated:human` route.
- Whole relevant-document metadata is currently loaded for a search; million-document latency/memory was not benchmarked. T02 supplies the bounded candidate vector search, but metadata indexing would be a separate optimization.
- The only observed warnings are the pre-existing Pydantic class-config deprecation and joblib's physical-core detection warning. No API credentials or external providers were required by the test fixtures.

## Fix round 1

Resolved the integration-test contract conflict under the controller's explicit authorization. Only `test_downstream_clustering_reads_compat_fields` in `backend/tests/test_integration_stage0_2.py` changed: it seeds prepared copies of the preprocessed documents, deterministic stage-three vectors through `VectorStore`, and accepted final Core labels through `LabelStore`, then calls the existing `POST /train/{sid}/export` endpoint with `withoutModel: true` before clustering. The test verifies the export counts, absent model, and persisted `training.exportRef`.

The original description-in-text assertion now checks clustering's TF-IDF text input, with explicit call/length verification outside clustering's exception handlers. The original successful-status, 200-document total, and nonempty sample `desc`/`cafe` assertions remain. Additional assertions check the complete clustered document-ID set and exact preservation of every document's `desc`, `cafe`, and `link`. No production code or parallel T13-owned files were edited; existing uncommitted T14 work was preserved. No network or git write commands were used, and no commit was created.

Commands run from repository root and output:

- `backend/.venv/bin/python -m pytest backend/tests/test_integration_stage0_2.py backend/tests/known -q`
  - `56 passed, 2 warnings in 6.96s` (exit 0; zero failures).
- `backend/.venv/bin/python -m pytest backend/tests -q --ignore=backend/tests/model --ignore=backend/tests/label` — run once.
  - `897 passed, 2 warnings in 108.69s (0:01:48)` (exit 0; zero failures).
- `git diff --check -- backend/tests/test_integration_stage0_2.py`
  - No output (exit 0).

Both pytest runs reported only the existing Pydantic class-config deprecation and joblib physical-core detection warnings. The prior unresolved integration-test conflict is resolved; both requested validation runs pass.
