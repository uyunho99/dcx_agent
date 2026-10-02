# T7 report

Status: COMPLETE. No git add or commit performed. Rerank files were not modified.

## Changes

- Added `backend/app/evidence/tagging.py`, `quotes.py`, and `prompts/tag.v1.md`.
- Added tests first in `backend/tests/evidence/test_quotes.py` and `test_tagging.py`.
- Tagging uses the `evidence.tag` registry task and Pydantic output schema, with the exact shared input limits (8 documents, body 1,500 characters, first 10 prepared comments of 300 characters each, document KI summaries 200 characters). Statement KI text remains untruncated. No six-dimension tags are generated.
- Cached documents do not incur tagging calls. Tag cache remains preparation-scoped outside versions. Cached prepared excerpts support later per-item Known Insight judgment without rereading crawler data.
- ThreadPoolExecutor concurrency uses the explicit parameter, then `settings.evidence_llm_concurrency` when present, then `params.CONCURRENCY`. Workers only call the LLM; the calling thread performs tag, Known, and dims cache writes after collecting results. Serial and concurrent results are identical.
- Unknown response IDs are ignored per requested batch. Missing IDs alone are retried once in the next retry wave (batches never exceed eight). Persistently missing documents are absent from tags/cache and exposed as `untagged` count and `untagged_ids` for downstream selection/reporting.
- Quote matching normalizes whitespace while retaining original character spans. Returned offsets are half-open and refer to original prepared title/body/comment text; duplicate passages use the first match. Missing quotes have null offsets and `verified=false`. Comment indices are zero-based in stage-6 prepared list order.
- Existing dims override generated situation. State joins environment and task_goal with a space; emotion uses internal_state; barrier uses resource_constraint. Core-only lazy dims use the existing full dims prompt hash and cache schema, with origin `lazy`.
- Small shared-writer extraction in `backend/app/segment/dims.py`: sample extraction and lazy extraction now use the same SQLite row writer. Existing stage-6 behavior is covered by its regression suite.
- `judge_known` requests only missing (doc_id, ki_id) pairs, one KI per request group. A single positive `known_match` does not incorrectly cache negatives for other KIs. Request-local #k labels are converted to stable KI IDs for cached judgments and returned tag projections. `drop_known` plus the current Known list prevents stale matches from reappearing on tag cache hits.

## Validation

1. RED: targeted new tests failed collection with the two expected missing-module errors before implementation.
2. GREEN/refinement: corrected a test's manually miscounted exclusive quote end offset (10, not 11). Added retry recovery, invalid-schema/no-cache, deletion projection, and caller-thread lazy-write checks.
3. `backend/.venv/bin/python -m pytest backend/tests/evidence/test_quotes.py backend/tests/evidence/test_tagging.py backend/tests/segment/test_dims.py -q`: **41 passed**, one existing Pydantic deprecation warning.
4. Required full evidence command, run once: `backend/.venv/bin/python -m pytest backend/tests/evidence -q`: **135 passed**, two warnings (Pydantic config deprecation and joblib physical-core detection fallback).
5. `git diff --check`: clean.

## Integration notes and concerns

- No blocking concerns found. All tests use local fake responses; no live provider calls were made.
- T9/T11 callers must call `judge_known` for newly added statement KIs, call `TagCache.drop_known` on deletion, exclude absent tag IDs from selection, and put `TagResult.untagged`, `reason_counts`, and `lazy_dims` into the stage report. Those lifecycle/pipeline files are outside T7 ownership.
- `judge_known` resolves current KI text through the existing session Known store. Its required contract has no version argument.
- Backend exceptions intentionally propagate for the worker's pause/failure handling; unsuccessful/schema-invalid responses follow the bounded missing-document retry path.
- Concurrent work changed the worktree during this task; unrelated rerank, decision-log, and frontend changes were not edited or reverted.
