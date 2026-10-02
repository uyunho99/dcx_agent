# T3 implementation report

Status: COMPLETE — implementation, QA smoke checks, and required final tests passed.

## Scope and changed files

- Added `backend/tests/fixtures/evidence_synth.py`.
- Added `backend/tests/fixtures/llm/evidence.queries.json`, `evidence.tag.json`, and `evidence.novelty.json`.
- Added `backend/tests/evidence/test_fixture.py` (seven tests including parametrized cases).
- Updated `backend/tests/scripts/make_segment_qa.py` with optional `--confirm-all`.
- No production modules, existing segment tests, or other workers' files were edited by this task. No subagents, staging, or commits were used. No evidence test package initializer was needed.

## Implementation

`make_evidence_session(local_data_dir, **segment_kwargs) -> SynthSession` forwards all arguments to `make_segment_session`, runs the real segment pipeline with fake embedding settings and document-bound fake dims responses, and confirms every cluster, persona, and context. Names use drafts or the exact `CLn 이름` fallback. Persona desires/goals and context actions use drafts. `mark_done_if_complete` persists status `done`, completion, and confirmation counts. Local-storage settings, embedding settings, S3 local bindings, and the backend registry patch are scoped and restored even on exceptions.

`QueryEmbedder(session, vectors)` accepts a `SynthSession` and its prepared `VectorStore`. It computes normalized persona/context centroids from the stored fixture vectors using the generator's original assignments. It excludes zero-vector and no-token documents. Matching context vocabulary takes precedence over persona vocabulary; multiple matched owners at one layer average their directions. Token boundaries prevent C1/P1 matching C10/P10. Unknown text uses a normalized, SHA-256-seeded deterministic vector. `embed(texts, input_type='document')` returns float32 `(n, dim)` arrays and accepts query mode, including empty batches.

`fake_evidence_backend(contexts, docs=None)` returns an actual `FakeBackend(responses=...)`. Contexts are SegmentStore context rows; docs is the requested batch's `doc_id -> original document` mapping. Omitting docs supports query-only tests. Construct a helper backend for each requested batch when testing batching. Responses contain exactly the supplied document IDs and actual context IDs; no static-ID template replacement is used.

Queries include two desire-check sentences, one artifact sentence, all eight exact dimension keys, and all context anchors. Query text uses supplied keywords, removes the exact forbidden expressions, and uses first-person wording. The JSON key is `context_queries`, following the concrete `PersonaQueryOut` contract in the brief; the prose design calls the individual per-context object `context_query`.

Tags contain the exact requested fields and quote the first original sentence from body, title, or an indexed comment. Empty documents raise a clear ValueError instead of inventing a quote. Situation is supplied only when dims are absent; context_dims are supplied only for Core documents lacking dims (unlabelled generic examples default to Core). Artifacts are an empty valid list and known_match is `none`. Novelty responses use `high` with nonempty reasons. Static files are concrete generic examples for the default FakeBackend; runtime IDs/quotes come from the helper.

The QA script preserves the default stage-five-only path and existing JSON output. With `--confirm-all`, it uses `make_evidence_session(..., qa=True, seed=42)`.

## TDD and verification

1. Created fixture tests before implementation. Ran `backend/.venv/bin/python -m pytest backend/tests/evidence/test_fixture.py -q`: RED, collection failed with `ModuleNotFoundError: tests.fixtures.evidence_synth` (exit 2).
2. Implemented fixture, fake response examples, and QA option. The fixture tests passed: 6 passed.
3. Added a conditional-dims regression before the correction. Ran `backend/.venv/bin/python -m pytest backend/tests/evidence/test_fixture.py -q -k only_supplies`: RED, 1 failed / 6 deselected because situation was populated despite existing dims.
4. Corrected conditional dims. Final required fixture command: `backend/.venv/bin/python -m pytest backend/tests/evidence/test_fixture.py -q` — **7 passed, 2 warnings in 6.14s** (exit 0).
5. Ran the QA script as a subprocess twice in separate temporary directories, without and with `--confirm-all`. Both exited 0 and returned 1,200 documents with the same deterministic session ID. Default had no completed segment. Confirm-all persisted `segment.status=done`, `completion.segmentDone=true`, clusters **5/5**, personas **10/10**, contexts **34/34**. Temporary data was removed after inspection.
6. Final required segment command: `backend/.venv/bin/python -m pytest backend/tests/segment -q` — **221 passed, 1 deselected, 2 warnings in 136.13s** (exit 0). Run once at the end, as requested.
7. `git diff --check` emitted no whitespace errors.

Tests verify isolated storage/settings restoration, all confirmations and draft values, persona/context vector directions and nearest-centroid ranking, hash determinism, float32/empty output, ID-prefix collisions, all context anchors and exact query dimensions, forbidden words, requested document IDs, body/comment quote provenance, novelty values, default fixture loading through FakeBackend, and conditional dims behavior. Pytest's existing external-socket guard remains active.

## Concerns and integration notes

- T5/T7/T9 production output schemas do not exist yet in this worktree. Validation currently uses local Pydantic output envelopes plus field/content assertions against the brief and design. Future schema integration should verify nested nullability and artifact representation; this task does not preempt those modules.
- The fake response helper binds a supplied batch at construction time; it does not parse future prompt formats or filter arbitrary later task attachments. Pass the requested subset when constructing each batch backend.
- Fixture vector centroids follow original generator vocabulary assignments, not potentially renumbered segment IDs. This avoids confusing vocabulary ownership after clustering.
- Fixture generation temporarily patches global settings, as the existing segment fixture does; do not invoke generators concurrently in the same Python process.
- Other workers' changes are present in the shared worktree, including segment production/tests. They were left untouched; regression results describe the shared tree at execution time.
- Existing Pydantic class-config deprecation and joblib physical-core detection warnings appeared in fixture tests; neither caused failure.
