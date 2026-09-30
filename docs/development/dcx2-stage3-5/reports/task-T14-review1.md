### Spec Compliance
- ✅ Pinecone is gone. `pinecone_svc.py` is deleted, the `pinecone-client` line is removed from requirements, and `pinecone_api_key` is removed from Settings (diff:43, 883-912, 925). `test_no_pinecone_import` checks both `sys.modules` and `Settings.model_fields` (diff:1053-1056).
- ✅ The `KnownInsight` wire format matches 2.6: `id`, `type`, `text`, `doc_id`, `from` (alias), `createdAt`, `vectorRow`. `read_known` reads a legacy `list[str]` as statements (`app/known/models.py`, diff:185-199).
- ✅ Statement vectors are computed once when added and appended to the version-local `known_vectors.f16`. Doc items reuse the 3단계 vectors. A PATCH with unchanged text makes no embed call (store.py `_embed`/`_new`, diff:257-292; test at diff:1119-1125).
- ✅ The API has GET/POST/PATCH/DELETE `/known/{sid}`, with PATCH and DELETE on `/{sid}/{item_id}`. It uses `ContextRoute` for the error envelope, has extra='forbid' bodies, and shows the unconnected warning text from 6.1 (`routers/known.py`, diff:602-640).
- ✅ `post_context` makes exactly one init call (plus its local import). It copies statements from other sessions with the same bk, tagged `from=prev_session`, and never copies doc items (diff:575-576, 330-351).
- ✅ `search_docs(sid, queries, top_k, novel=True)`:
  - It searches only Core+Supporting: from the exportRef file, or else from `final` (diff:113-121).
  - Candidates are `top_k*3`. It excludes Known doc_ids and anything whose max cosine is ≥ `settings.known_theta`.
  - `novel=False` turns off only the Known filtering.
  - All four reasons are returned (diff:124-169).
  - Queries go to the embedder in one call (test at diff:1072-1077).
- ✅ Chat and insight-chat return `sources` items carrying `doc_id`, plus `reason`. `/search` returns `reason`. `novel` was added to all four request schemas (diff:421-447, 484-555, 659-661).
- ✅ New-session clustering reads only the exact file at `training.exportRef` (it checks `name == 'relevant.jsonl'` and that the path stays under `classified/{sid}`). It errors with "5단계 결과가 없습니다", never falls back, and never calls the embedder. Legacy sessions keep the old path (diff:91-101, 693-710). Tests cover no embed calls, Core+Supporting-only input, and the missing-export error with the fallback mocked to fail (diff:1035-1050, 1087-1100).
- ✅ `run_embedding` completes immediately with "3단계 벡터 사용" (diff:818-821).
- ✅ Personas send all cluster queries in one `search_docs` call (diff:855-857; test at diff:1144-1156).
- ✅ The integration test `test_downstream_clustering_reads_compat_fields` was not weakened. The original assertions are all still there:
  - each doc's `desc` appears in its clustering input text (now checked at the TF-IDF input instead of the embedding mock; it is the same text built the same way);
  - `status == 'done'`;
  - `total == 200`;
  - every sample has a non-empty `desc` and `cafe`.
  
  The input docs are still the real preprocessed output from `full_flow`, so the compat fields are genuine. The test also adds new checks: the full doc_id set, exact `desc`/`cafe`/`link` preservation, and the export counts (diff:1225-1270).
- ✅ The "Known Insight" name is used in API messages (D-135).
- ⚠️ Cannot verify from diff: that the full suite passes from the repo root (1138 claimed). The report's own runs use `cd backend` and `--ignore` flags. Also not verifiable here: whether `routers/prep._root` and the `sessions/` directory layout used in `initialize` match `root_dir()`, and the claimed absence of deadlocks with the non-reentrant `flock` (the tests passing suggests none).

### Strengths
- Legacy handling is clean. A missing `derivedRef` gives `no_vectors`, and legacy clustering keeps the old path unchanged.
- The exportRef read is bounded to the session's own tree and exact filename, so the `all.jsonl` sibling can never be read as input.
- Vector bytes are fsync'd before the row pointer is saved in session.json. Orphaned rows are harmless.
- Failed statement embeddings keep the statement and show the design's warning text.
- The tests are behavioural and meaningful, e.g. a fake embedder that raises if called and a fallback mock that raises if used.

### Issues
#### Critical
None.

#### Important
1. **Persona generation has lost its evidence for legacy sessions (and for any search reason other than all_known)** (`services/personas.py`, diff:869-872).
   - Before: when RAG returned nothing, each cluster fell back to `clusters[cid][:20]`.
   - Now: `items = rag_docs` with no fallback. Legacy sessions always get `no_vectors`, so every cluster section in the persona prompt is empty. That breaks the ruling that legacy sessions keep their old paths.
   - The same happens for new sessions when the reason is `embedder_unconnected` or `no_labels`.
   - The comment's justification (not letting Known documents back into the prompt) only holds for `all_known`.
   - Fix: fall back to the raw cluster docs, with Known doc_ids removed, when `reason in {'no_vectors', 'no_labels', 'embedder_unconnected'}`. Keep the fallback off for `all_known`.
   - Add a legacy persona test. The existing `test_personas_queries_batched` only covers `all_known`.
2. **`search_docs` holds the session `flock` for the whole search, including the network embed call, and scans everything on every call** (`known/filter.py`, diff:126-169).
   - Each chat or search request does all of the following under the lock:
     - a full `iter_shards()` pass just to build `valid`, which is redundant because `cosine_topk` already skips zero, failed and non-allowed rows;
     - a full JSON parse of every prepared `docs/*.jsonl` when there is no exportRef, or of the full export file;
     - the Voyage query call;
     - a second full pass inside `cosine_topk`.
   - At the planned scale (about 31만 docs) this is seconds of work and hundreds of MB per chat message. Every session writer (drafts PATCH, Known CRUD, and possibly T11 per-item commits) is blocked meanwhile.
   - Fix: take a snapshot of `data` under the lock and release it before embedding and scanning. Drop the pre-scan and derive `no_vectors` from an empty `cosine_topk` result together with `vectors.count()`. The implementer flagged the metadata load, but nothing is recorded as follow-up.

#### Minor
1. `initialize` and `add` make embed calls (one per statement, not batched) while holding the session lock inside `POST /context` (store.py:348-350). A slow provider delays session creation. Batching the statements into one embed call would fix this.
2. Legacy items get a new `createdAt=now()` on every read until they are saved. Also, `context_patch` items without `createdAt` get a timestamp that changes per read in any path that skips `initialize` (models.py:192).
3. A stale or invalid `exportRef` makes `search_docs` raise `StoreError` instead of returning a reason. That escapes `/search` as a 500 without the error envelope, and fails the whole persona job, where the old code caught RAG errors (filter.py:94-100, search.py:660, personas.py:857).
4. Empty persona queries (clusters with no `kw`) are sent to the embedder as empty strings. Voyage may reject them, which would then show up as `embedder_unconnected` or an error.
5. Known Insight CRUD on a legacy session fails with the stage 0~2 edit message from `assert_writable` ("구버전 세션은 0~2단계를 편집할 수 없습니다"), which is misleading in this context.

### Assessment
**Task quality:** Needs fixes

**Reasoning:** Everything in the spec and the controller rulings is implemented and tested, and the integration test's original compat-field assertions are intact. However, the persona path now drops all cluster evidence for legacy sessions (and when the embedder is unconnected), which regresses the "legacy keeps old paths" ruling. Search also holds the session lock across a network call and full-store scans on every request.
