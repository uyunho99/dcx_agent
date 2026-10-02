# T3 report — completed

Implemented `backend/app/persona/grade.py` and test-first coverage in
`backend/tests/persona/test_grade.py`. No other worker's files were changed;
no staging, commits, or subagents were used.

## Behavior and integration contract

- `grade_field(field, cites, refs)` implements the design 5.3 table using T1
  `EvidenceRef` objects. Observation-capable fields require at least one verified
  quote. Valid unverified citations and inference fields yield inferred.
  Missing citations, dangling references, intent, and persona_profile yield
  speculated. Unknown field names conservatively yield speculated.
- `traceable_support(fields, refs)` counts non-null text cells with nonempty,
  fully resolvable citation lists, divided by all non-null text cells. Empty or
  all-null input yields 0.0. Unverified references still count as traceable.
- `grade_card(card, refs)` takes the 5.2 `contexts` list and top-level summary
  fields and returns `{grades, summary, traceable_support, trace}`. `grades`
  maps Context IDs to field grades; `summary` maps top-level field names to
  grades; `traceable_support` maps Context IDs to ratios. Only a Context below
  0.5 is downgraded, exactly one step, with speculated as the floor. Summary
  fields are not subjected to Context downgrades. Null cells have no grade.
- Trace rows contain `{context_id, field, evidence_id, evidence}`. The nested
  evidence is a detached `EvidenceRef.model_dump()` preserving the package
  quote, document, source, role, verified flag, and source context. The outer
  context identifies the graded cell (null for summary). Citations are
  deduplicated per cell; dangling references do not produce trace rows.
- The functions do not mutate card inputs or references and perform no I/O.
- T2's `params.py` became available during implementation. The final module
  imports `OBSERVED_FIELDS`, `INFERRED_FIELDS`, and `TRACE_MIN` from it. No local
  fallback constants remain and T2's file was not edited.

## TDD and verification

1. Wrote the parametrized grade table and support/card tests first.
2. RED: requested pytest command exited 2 with
   `ModuleNotFoundError: No module named 'app.persona.grade'` before implementation.
3. GREEN: implementation passed all 27 cases.
4. Refactored constants to imports from T2; final requested command:
   `backend/.venv/bin/python -m pytest backend/tests/persona/test_grade.py -q`
   — **27 passed, 1 warning in 1.93s**.

Coverage includes the brief's exact table, support 0.4 lowering observed and
inferred, the inclusive 0.5 non-downgrade boundary, Context isolation, empty/null
cells, unverified and duplicate citations, mixed valid/dangling references,
summary/profile grades, determinism, input immutability, and trace provenance.
Tests run under the existing external-network guard without keys or LLM calls.

## Concerns / explicit interpretations for T5

- The supplied design names `trace[]` but does not define its exact row schema.
  This implementation uses the above explicit linkage plus an Evidence Package
  snapshot; T5 should persist the returned grades/summary/support/trace fields.
- Mixed valid/dangling citation lists conservatively yield speculated and do
  not count as a supported field, while retaining resolvable trace entries.
  Null cells are excluded from the support denominator. These unspecified edge
  cases are fixed by tests and documented in function docstrings.
- Citation validity means membership in the Persona-wide reference index. The
  design does not require same-Context citations or exclude counter/rare roles;
  provenance is preserved so downstream consumers can distinguish them.
- The sole warning is the existing class-based Pydantic config deprecation in
  `backend/app/config.py:12`, unrelated to this change.
