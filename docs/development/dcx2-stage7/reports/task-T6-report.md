# T6 candidate search report

Status: implemented; T6 tests pass. Full evidence-suite verification is blocked by missing modules owned by parallel tasks.

## Changes

- Created `backend/app/evidence/candidates.py` with `search_context(...)` and `search_persona(...)`, sharing one retrieval implementation.
- Allow sets come exclusively from the requested Context/Persona metadata; exclusions are passed to `filtered_topk`, the only search entry used.
- All query texts are embedded in one call with `input_type='query'`.
- Per-query hit ranking applies `CORE_BONUS = 0.05` for `band='core'`, except for `Counter`. Defaults remain `TOP_PER_QUERY = 15` and `CANDIDATES_M = 50`, imported from params.
- Hit lists are unioned and deduplicated. Relevance is the maximum raw cosine across every query, including queries where the document missed the hit cutoff. Both hit and final cutoffs resolve ties by doc_id.
- Output records contain doc_id, relevance, unique dims_hit in query order, and the original band.
- Owners smaller than m retain all searchable, non-excluded documents per the brief's small-Context requirement. Supplemented documents have empty dims_hit unless they actually made a per-query hit list. Missing, failed, and zero vectors remain excluded by the search wrapper.
- Created `backend/tests/evidence/test_candidates.py` with the seven required cases, small-Context cases at 3/23/49 documents, and boundary/edge cases.

## TDD and validation

1. Wrote tests before implementation.
2. RED: `backend/.venv/bin/python -m pytest backend/tests/evidence/test_candidates.py -q` failed collection with `ModuleNotFoundError: app.evidence.candidates`.
3. Implemented candidates. Initial run: 18 passed, 1 failed because one test compared stored float16 cosine against unquantized input with an overly tight tolerance. Corrected the expectation to use the stored vector.
4. GREEN: same targeted command completed with **19 passed, 1 warning**. Shared implementation reviewed; no further refactoring needed.
5. Ran the requested `backend/.venv/bin/python -m pytest backend/tests/evidence -q` **once**. It stopped with **2 collection errors**: `test_queries.py` imports missing `app.evidence.queries`; `test_rerank.py` imports missing `app.evidence.rerank`. Neither file was modified by T6.
6. `git diff --check` reported no errors (new T6 files are untracked). No git add/commit performed.

The warning is the existing class-based Pydantic Settings config deprecation in `backend/app/config.py`.

## Concerns / integration notes

- Full evidence-suite success remains unverified until the parallel query/rerank implementations are available.
- To enforce doc_id ties before truncation and raw maximum cosine across all queries, candidate search requests all owner-scoped scores through filtered_topk, then applies the bonus and top-15 cutoffs locally. This uses memory proportional to query count times owner document count; it avoids changes to the committed search entry point. No performance benchmark was requested or run.
- The small-owner fallback explicitly implements the brief's “all documents” requirement for owners below m; dims_hit still means actual top-per-query hits.
- Only the two T6 source/test files and this report were written. Parallel query/prompt/rerank files were left untouched.
