# T5 report

Status: complete. No git add/commit. No subagents. Other workers' files were not modified.

## Delivered

- `backend/app/persona/cards.py`: `generate_card(sid, block, *, run_task=None) -> CardResult` with `status` (`done`/`failed`), `card` (dict or None), and `error` (failure kind or None).
- `backend/app/persona/prompts/card.v1.md` and `summary.v1.md`.
- `backend/tests/persona/test_cards.py`: 25 tests including all nine brief cases and additional failure, reference, ratio, and registry checks.

Card generation splits Contexts into chunks of at most CARD_CHUNK=4, calls persona.card for each, then persona.summary once on success. Chunk evidence contains Context support/counter/rare references, numbered locally from E1; code remaps to evidence_index's Persona-wide numbering (which includes Desire support first). Summary references use the Persona-wide namespace. Trace snapshots and grades come from grade_card. Confirmed identity, Desire, Goal, Action, and metrics are copied from the package. No persistence occurs here; a failed call returns no partial card.

Output schemas reject unexpected fields, invalid ordinal sensitivity, journey ratios outside [0,1] or not summing to one, partially-null ratios, incomplete/duplicate Context coverage, foreign Context citations, and unknown summary references. Journey may have all three values null. Contexts without evidence have null cells; a Persona with no evidence has null summary attributes. Prompts use explicit field projections so unknown package extras, including targetScope/projectContext, cannot leak into either task. Intent includes the fixed `의도 ≠ 행동` warning.

## TDD and verification

1. Wrote tests before implementation; RED: collection failed with `ModuleNotFoundError: app.persona.cards`.
2. Implemented module/prompts; focused suite passed (22 tests).
3. Added registry retry, later-chunk atomic failure, and evidence-empty summary coverage; focused suite passed (25 tests).
4. Refined null preservation and explicit counter-Context input; ran the requested final command exactly once:
   `backend/.venv/bin/python -m pytest backend/tests/persona -q`
   Result: **134 passed, 1 warning in 3.08s**. No concurrent-worker test failures.

Existing warning: Pydantic class-based Settings config deprecation in `backend/app/config.py`.

## Integration notes / concerns

- The default registry already makes two parse/schema attempts. Generation invokes that runner once per logical call; injected runners are defined as single-attempt callables and receive up to two attempts. Backend failures/exceptions fail only this Persona without retries. A later valid Persona can continue independently.
- The shared `fake_persona_backend` emits Persona-wide E numbers by design, whereas D-302 requires chunk-local card numbers. T5 tests adapt its output into local numbers before validating production output schemas. The shared fixture was not modified. Pipeline tests using that fake directly must apply the same local-number adaptation for persona.card; summary numbers already match.
- For dims-derived non-null situation values, code conservatively retains the original text rather than trusting an unrestricted semantic rewrite. Generated null remains null. This enforces the original meaning/range but deliberately does not provide stylistic rewriting of existing dims values.
- Confirmed values are copied from the package contract. Detecting later changes to stage-six confirmations and marking stale remains T7's documented responsibility.
