# T11 report

Status: COMPLETE. Implementation and verification passed.

## Implementation

- Added `backend/app/routers/stage8.py` and registered it in `app/main.py`. All persona and insight routes in the brief are present, with version-local reads, writable-version checks, structured StoreError responses, and worker dispatch through `app.work.runner`.
- Persona run requires an Evidence Package and returns `evidence_required` with the exact copy: `근거 탐색을 마친 뒤 페르소나를 만들 수 있습니다.` Active same-kind work returns `running`; other active work in the version returns `locked`. Retry checks both persisted run IDs through `pipeline.assert_run` before dispatch.
- Persona status projects worker state, individual errors, and the stage-eight report. Pending/failed cards supply `card: null`. Source reconciliation detects changed evidence/confirmed identities on status and before insight execution; historical reads remain immutable.
- Insight derive/concept work requires completed, non-stale personas. Chat, target-specific revert, and confirmation use the committed domain modules. Insight reads expose revision/history envelopes, opportunity bars, and radar values keyed by insight ID.
- Added `GET /known/{sid}/suggestions`: other sessions only, matching project-context bk (legacy top-level fallback), confirmed insight IDs only, active source versions, stale results excluded. Sort descending by insight `savedAt` (fallback session `updatedAt`), with session/insight IDs as deterministic tie breakers. Deduplicate exact titles before selecting at most 20 results.
- Suggestions do not initialize/copy confirmed insight artifacts into Known. Existing previous-session Known-statement inheritance remains unchanged. POST accepts `from: prev_session` for statement additions only; ordinary statement/doc origins remain drawer/rag.
- Added `backend/tests/known/__init__.py`, following the segment test package convention to prevent module-name collisions.

## Frontend contract decisions

Read `frontend/src/lib/api/persona.ts`, `insight.ts`, `known.ts`, and `types.ts`; frontend files are unchanged. The broad camelCase instruction does not apply to all nested fields in the actual frontend contract: preserve `package_run`, map point `context_id`/`persona_id`/`cluster_id`, `pain_point`, `context_ids`, prescription and concept fields exactly as typed. Public `runId`, `stage8`, and suggestion `sessionId`/`insightId`/`painPoint` retain their camelCase names. No endpoint-path or request-body discrepancy was found.

## TDD and verification

1. Wrote both requested test files before implementation. First focused run: **14 failed**, proving the absent routes/contracts (3.40s).
2. Implemented routes/store integration. Focused run: **14 passed** (6.67s).
3. Added edge coverage for changed source without status polling, worker states, incomplete cards, insight conflicts/chat failure/concept revert, version-specific suggestions, readonly adds, and stale/project-bk filtering. Observed **1 failed, 18 passed** for the source-change gate, then fixed it.
4. Final focused run: **19 passed**, 1 existing Pydantic deprecation warning (5.27s).
5. Full backend suite: **1949 passed, 2 deselected, 2 warnings in 281.21s (0:04:41)**; exit code 0. Command (run once): `backend/.venv/bin/python -m pytest backend/tests -q`.
6. `git diff --check` passed. No frontend changes, git add, commits, or subagents.

## Concerns / scope

- Suggestion recency uses available insight publication timestamps; the committed confirmation API does not store a separate per-insight confirmation timestamp.
- Existing Known-statement inheritance is retained for compatibility; new confirmed insight artifacts are suggestion-only until explicitly added.
- HTTP tests use local synthetic persona generation and stub worker dispatch. Existing domain/worker tests cover insight computation; no external providers or keys are used.
