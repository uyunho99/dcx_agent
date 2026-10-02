# Stage 8 browser QA fix round 1

Status: complete; QA-F1–F6 and rereview m1–m3 implemented and verified.

## Changes

| Item | Result |
| --- | --- |
| QA-F1 / D-318 | FakeBackend selects task-specific echo markers when attachments exist. Cards use each chunk's Context IDs and local E-numbers; summaries use Persona-wide references; derivation uses supplied Context IDs; concepts use supplied evidence (including qualified multi-Persona references) and journey Contexts. Original JSON fixtures and explicit response overrides remain supported. |
| QA-P6 / blocked prescription | `make_persona_qa.py` marks only Persona 4 (`CL0-P3`) with `[QA-P6:invalid-card]` in its confirmed name. Its card intentionally fails schema validation, including retries. Persona 1 (`CL0-P0`) retains the deliberate constraint violation; Personas 2–3 have valid, unblocked prescriptions. Both normal and ten-Context packages are covered. |
| QA-F2 | Concept failures remain visible when the matching terminal worker response arrives during a pending launch, including a response without a run ID. Polling clears that pending state. Pipeline and supervisor fallback failures use `컨셉을 만들지 못했습니다. 다시 시도하세요.`; derive retains the insight wording. |
| QA-F3 | Blocked prescription text remains visible under `차단된 처방`, struck through and muted with the existing `--sub` token. Constraint reasons remain visible; active metric, contribution and journey presentation is omitted. |
| QA-F4 | Header verdicts are `✓ 통과`, `⚠ 검토`, `✕ 차단`. |
| QA-F5 | Revision sources are `생성`, `채팅 수정`, `되돌리기`; timestamps use ko-KR date/time in the browser's local timezone. Chat messages remain visible. |
| QA-F6 | Persona's `인사이트 도출` checks the selected version's insight revision, starts derive if absent and no worker is running, then navigates. Existing revisions only navigate. Mutation guards remain in effect. |
| m1 | The launch API durably registers its accepted run, mode and target if the worker has not already published a checkpoint. A supervisor failure before worker preflight completes now matches the current run. Fast-worker checkpoints and reset/old-run filtering remain intact. |
| m2 | SQLite errors from both stale reconciliation and confirmation comparison become HTTP 409 with kind `evidence_unavailable` and Korean copy `근거 상태를 확인하지 못했습니다. 다시 시도하세요.` |
| m3 | Both missing-evidence and stale-evidence guidance hide `근거 탐색으로` in read-only versions. |

## Validation

- Added regression tests before implementation and observed failures for the requested behavior. Updated existing English verdict and generic concept-failure expectations to the new contract.
- Tests cover chunked cards, one intentional failure, blocked versus unblocked prescriptions, arbitrary Context IDs, I3 and multi-Persona concepts, early worker failure, both SQLite error paths, pending concept failures, localized revisions, derive-on-navigation and read-only guidance.
- Final compatibility review found and fixed an echo-dispatch regression: explicitly injected malformed JSON must still return `parse`, not `schema`. A failing regression test was added first; the targeted fake/Persona suite was rerun afterward.
- `backend/.venv/bin/pytest backend/tests -q`: **2,015 passed, 2 deselected**, 303.73 seconds. Existing Pydantic deprecation and joblib CPU-detection warnings were emitted.
- Final fake-response compatibility check (`backend/tests/persona/test_qa_fix1.py backend/tests/llm`): **36 passed**, including the additional parse-contract regression introduced during full-suite execution.
- `npm --prefix frontend test`: **59 files, 591 tests passed**.
- `npm --prefix frontend run lint`: **passed**.
- `next build` skipped as requested.

## Controller follow-up and limits

- Restart the QA backend to load the changed Python implementation. Port 8321 was not stopped or restarted by this task.
- Generate a new QA session with the script (use an unused seed or a fresh data directory). Existing sessions do not acquire the QA-P6 identity marker automatically. Example: `backend/.venv/bin/python backend/tests/scripts/make_persona_qa.py LOCAL_DATA_DIR --seed 43`; add `--big-persona` for chunking.
- The marked Persona deliberately continues failing on retry. No real model is used by the echo path; it produces deterministic QA content and does not assess actual constraints.
- Browser QA at ports 3321/8321 was not rerun here; verification used automated component, API and pipeline tests. The controller should recheck the visual flow after restart and data regeneration.
- No git add/commit, subagents, or production-data edits. Pre-existing decision-log and rereview-report changes were left untouched.
