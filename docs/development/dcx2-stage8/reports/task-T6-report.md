# T6 report — completed

Implemented design sections 5.1, 5.4 and 9 within the T6-owned files:

- `backend/app/persona/prescribe.py`
- `backend/app/persona/prompts/prescribe.v1.md`
- `backend/app/persona/prompts/constraint_check.v1.md`
- `backend/app/persona/prompts/scope.v1.md`
- `backend/tests/persona/test_prescribe.py`

`prescribe(sid, card_summary, project_context, *, run_task)` issues separate `persona.prescribe` and `persona.constraint_check` tasks using Pydantic output schemas. A `violates` verdict triggers exactly one new prescription with the prior prescription and all violation reasons, followed by another constraint check. `review` does not block or trigger repair. Final verdicts are returned under `constraint`, with `blocked` and `represcribed` booleans. Persistent violations add `message` using the exact copy:

> 사내 제약 '의료적 효과 표현 금지'를 지키는 처방을 만들지 못했습니다.

For multiple remaining violations, the same template is applied once per constraint, joined with newlines. The check must cover every distinct input constraint exactly once; missing, duplicate or unknown constraints fail instead of being treated as compliant.

`scope_check` issues only `persona.scope`, with card summary plus `targetScope`, `productCategory`, and `positioning`. It returns the specified `{verdict, reason}` contract. `outside` is the downstream header's FUTURE condition; UI rendering is outside T6 ownership. Prescription inputs contain only card summary, `analysisGoal`, `keyMetrics`, and `constraints`; constraint checks receive only the draft and constraints. ProjectContext models and JSON mappings are supported.

All calls use `LLMTask`, with the registry as the default runner and an injectable `run_task`. Failed calls raise `PrescriptionError` for downstream workers to handle, without mislabeling failure as a verified prescription or a persistent constraint violation. Registry schema retries remain separate from the single business repair. Korean prompts specify JSON fields and forbid generated metric values, source quotations and basis.

## TDD and verification

1. Wrote the tests first and ran the required command: RED, collection failed with `ModuleNotFoundError: app.persona.prescribe`.
2. Implemented the module and three prompts: GREEN, 13 passed.
3. Removed redundant test assertions and added repaired-to-review and registry schema-retry coverage: 17 passed.

Final command:

`backend/.venv/bin/python -m pytest backend/tests/persona/test_prescribe.py -q`

Result: **17 passed, 1 warning** (2.25 seconds). Tests run with fake responses and no external network or keys. Coverage includes the five named brief cases, successful/no-repair paths, second-check review, isolated context inputs, empty constraints, incomplete checks, backend failures and malformed outputs. `git diff --check` also exited successfully.

## Concerns / integration notes

- The existing warning is the class-based Pydantic config deprecation in `backend/app/config.py`; unchanged by T6.
- Downstream T7 should catch `PrescriptionError` to mark a failed item; persistent violations are normal returned results with `blocked=True` and `message`.
- Downstream UI should map scope `verdict == 'outside'` to `[FUTURE]`; no extra scope field was added beyond the required contract.
- No edits to other workers' files; no git add or commit; no subagents.
