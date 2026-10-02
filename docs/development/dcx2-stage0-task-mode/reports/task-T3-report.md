# Task T3 report

Status: complete. R1 now uses r1.v2 and adds the exact task-mode focus from design section 4 immediately after the tone line. Unknown or missing modes produce an empty line; R2–R4 instructions are unchanged.

## RED

Command (before implementation):

```sh
backend/.venv/bin/python -m pytest backend/tests/keywords/test_task_focus.py backend/tests/keywords/test_prompts.py -q -p no:cacheprovider
```

Actual result: **20 failed, 28 passed, 1 warning in 0.57s**. Sixteen new prompt cases failed because RoundInputs lacked task_mode; the two existing version/template expectations failed as intended. The two session cases also exposed a test setup error: passing a minimal projectContext to update_session invokes full context validation.

## GREEN

Initial full run:

```sh
backend/.venv/bin/python -m pytest backend/tests/keywords backend/tests/context -q -p no:cacheprovider
```

Actual result: **2 failed, 489 passed, 2 warnings in 20.57s**. Only the two new session fixtures failed validation. Corrected their setup to initialize the session, then write the minimal stored context with store.write_json, following the existing test_rounds_api.py pattern.

Final command:

```sh
LLM_BACKEND=fake backend/.venv/bin/python -m pytest backend/tests/keywords backend/tests/context -q -p no:cacheprovider
```

Actual result: **491 passed, 2 warnings in 20.51s**, exit 0. Tests use isolated temporary session storage and the existing external-network guard. No real LLM calls were needed.

Additional verification: TASK_FOCUS values match design section 4 character for character; r1.v1.md has no git diff; scoped git diff --check passes. Tests verify template identity after removing the inserted line, legacy formatted output, both complete focus strings and their placement, role/domain restrictions for both modes, later-round instruction identity, and stored taskMode propagation/defaulting.

## Files changed

- Created backend/app/keywords/prompts/r1.v2.md: byte-for-byte copy of r1.v1.md with only the task_focus line inserted.
- Modified backend/app/keywords/prompts.py: version selection, exact TASK_FOCUS mapping, optional final RoundInputs field, R1-only interpolation.
- Modified backend/app/keywords/rounds.py: only _inputs, forwarding ctx.get('taskMode').
- Modified backend/tests/keywords/test_prompts.py: only the two authorized expectations. The new version and template filename are required because R1 now selects r1.v2.
- Created backend/tests/keywords/test_task_focus.py: 18 parametrized cases.
- Created this report.

## Concerns

No blocking concerns. Two warnings remain in untouched code: Pydantic class-based configuration deprecation and joblib physical-core detection fallback. Concurrent T5 frontend changes were observed and left untouched. No git add/commit or agent delegation performed.
