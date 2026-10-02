# T10 — Chat revisions and insight worker

Status: complete. Implementation and full backend validation passed.

## Implementation

- Added `backend/app/persona/chat.py`: `edit(sid, version, target, message, *, run_task)` uses registry-backed `insight.edit` with current revision JSON and the user message. Insight edits use `DeriveOut`; concept edits use `ConceptOut` and include the editable text projection and evidence references.
- Schema failures, invalid evidence numbers, unknown insight context IDs (Review Focus 3), duplicate insight/context IDs, invalid insight counts, and AS-IS contexts outside the target insight reject the edit without changing the revision. Exact failure message: `요청을 반영하지 못했습니다. 다르게 말해 주세요.`
- Successful edits append a new revision with `by: chat`, timestamp, and message. Both successful and rejected attempts append a row to version-local `persona/chat.jsonl`.
- Extracted `insights.recompute` from the existing derivation implementation so generation and edits share radar, percentile, ODI/bar mean, target, and known-badge calculation. Concept edits reuse package evidence hydration and basis calculation, recompute 4D counts, and rerun the public constraint checker.
- Added `chat.revert`: insight snapshots become new revisions through `PersonaStore.revert`; a concept target restores only that concept, preserving other current concepts and the complete history.
- Added `backend/app/persona/prompts/edit.v1.md` with schema, evidence/context, and code-owned-field rules.
- Added `backend/app/persona/insight_pipeline.py` and registered `insight` in worker KINDS. Modes are `derive` and `concept`; concept accepts a single target, a list, or all existing insights when omitted. Published revisions/items are durable resume checkpoints. Existing generated units are skipped, so queued concurrent runs do not regenerate completed units.
- A separate per-session `.insight.lock` serializes worker runs, chat edits, and reverts across threads/processes. It does not hold `sessions.locked` while calling PersonaStore mutation methods. Worker calls honor cooperative stop/pause boundaries; provider outages preserve checkpoints and set interrupted status with the existing exact LLM reason. Schema failures set failed status.
- Session insight status retains confirmed IDs, publishes the insight revision and savedAt, and updates insight completion on success.

## TDD and validation

1. Wrote `backend/tests/persona/test_chat.py` before implementation.
2. RED: `backend/.venv/bin/python -m pytest backend/tests/persona/test_chat.py -q` exited 2 because `app.persona.chat` did not exist.
3. Implemented and refactored shared metric recomputation. Focused chat/insight/concept run: **51 passed, 1 warning**.
4. Added provider recovery, concurrent chat revision, concept-only revert, and Persona prerequisite coverage. Final T10 run: **20 passed, 1 warning**.
5. Full backend suite, run once with `backend/.venv/bin/python -m pytest backend/tests -q`: **1930 passed, 2 deselected, 2 warnings in 282.95s (0:04:42)**; exit code 0.
6. Backend tracked diff whitespace check passed.

## Scope and concerns

- API router integration and revision-list/revert UI belong to T11/T13–T15. This task exposes the backend functions and worker kind for those callers.
- No frontend files were edited by this task. Concurrent frontend changes were left untouched. No git add or commit was run.
- No blocking concerns. Full-suite warnings were the existing Pydantic class-based configuration deprecation and joblib physical-core detection fallback. Two tests were deselected by suite configuration.
