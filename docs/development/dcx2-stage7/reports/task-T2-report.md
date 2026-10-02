# T2 report — embedder input type and filtered evidence search

Status: COMPLETE. Implemented in `/Users/persona1/Desktop/dcx_agent-stage7`, branch `feature/dcx2-stage7`. No staging or commits; no subagents.

## Requirements and scope

Read `.superpowers/sdd/03-plan/task-T2-brief.md` and `docs/development/dcx2-stage7/02-design.md`, including section 4. Applied the controller's D-256 ruling over the design's generic instruction to pass input type: existing document vectors were embedded without that keyword, so document requests must continue to omit it.

Changed only these implementation/test files:

- `backend/app/vectors/embedder.py`: Protocol, VoyageEmbedder, and FakeEmbedder accept `input_type: Literal['document', 'query'] = 'document'`. Voyage forwards the argument to the service; FakeEmbedder ignores it and retains deterministic output.
- `backend/app/services/voyage.py`: `get_embeddings(texts, input_type=None)` accepts the optional input type. Only query mode adds `input_type='query'` to every Voyage batch. Default and explicit document mode retain the previous request kwargs. Existing batching, truncation, blank-text substitution, validation, and error handling remain intact.
- `backend/app/evidence/__init__.py`: creates the evidence package.
- `backend/app/evidence/search.py`: adds the required `filtered_topk` signature, with `exclude=frozenset()` and `bonus=None`. Rejects `allow=None` with exactly `ValueError('allow set required')`. Delegates unchanged to the existing search when no bonus is supplied. With bonuses, retrieves all eligible scores, adds each document's bonus, ranks descending, and applies the requested cutoff.
- `backend/tests/evidence/test_search.py`: adds 15 test cases.

`backend/app/vectors/search.py`, existing embedder tests and their expected kwargs, and `backend/tests/evidence/test_fixture.py` were not modified. Existing unrelated segment/decision-log changes were left untouched. No parameters file or other task's functionality was introduced.

## TDD and validation evidence

1. Wrote all new tests before implementing production changes.
2. RED command: `backend/.venv/bin/python -m pytest backend/tests/evidence/test_search.py -q`
   - Exit 1: **3 failed, 12 errors**, 1 warning, 1.26s.
   - Failures confirmed absent embedder arguments and evidence module; fixture setup errors were the expected missing module.
3. Implemented the narrow changes.
4. GREEN, same command:
   - Exit 0: **15 passed**, 1 warning, 1.32s.
5. Refactor review: retained the thin wrapper and existing scoring implementation; no further refactor was necessary.
6. Required regression command, run exactly once:
   - `backend/.venv/bin/python -m pytest backend/tests -q -k "embed or vector or known or prep or search or voyage"`
   - Exit 0: **206 passed, 1533 deselected, 2 warnings**, 32.46s.
7. `git diff --check`: passed.

Tests cover default/explicit document compatibility, fake query equivalence, exact Voyage kwargs for both batches of a 129-text request, query mode, float32 shape, mandatory allow validation, and recursive static enforcement that only evidence/search.py contains the prohibited direct-search function name. Randomized filtering uses 1,000 documents, allow sets of 50, and 100 trials each with and without bonuses. Further checks cover exclusion, bonus promotion from outside the original top-1 across shards, adjusted returned scores, failed/zero vectors, empty allow/query inputs, nonpositive top-k, and exact legacy result/order parity when bonuses are absent or empty.

Tests used fake clients and the existing socket-blocking conftest; no API keys or external network calls were required.

## Decisions and concerns

- D-256: document and default calls omit the provider keyword; query calls include exactly `input_type='query'`.
- Bonus ranking must consider every eligible document before truncation. Chose reuse of the unchanged cosine implementation with `top_k=len(allow)` rather than duplicating its filtering/scoring code. Bonus-path result storage can therefore grow as O(number of queries × eligible documents); large-context performance was not benchmarked in T2. The no-bonus path retains the original bounded search behavior.
- Scores after bonuses are not clipped back to the cosine range; `CORE_BONUS=0.05` is tested verbatim. The wrapper accepts caller-supplied bonuses rather than owning that tuning constant.
- Adjusted-score ties retain stable base-search order. No additional document-ID tie policy was specified for this wrapper.
- No blocking concerns. The regression warnings concern existing Pydantic class-based config deprecation and joblib physical-core detection falling back to logical cores.
