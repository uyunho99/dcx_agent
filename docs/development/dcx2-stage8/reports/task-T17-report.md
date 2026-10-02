# T17 — Join bundle 2 / stage 7

Status: implementation and verification complete; controller staging required to clear Git's unmerged index entries.

## Changes

- Resolved all six conflicted working files, retaining segment/evidence/persona/insight worker dispatch, evidence and stage8 routers, all four completion flags, both frontend contract families, and one fake-response dispatch covering segment dimensions, evidence builders, and persona/insight builders.
- Reviewed the auto-merged version restart and comparison logic: stage 7 and stage 8 comparisons coexist; restart removes completion/artifacts at the appropriate stages. Strengthened restart tests to cover all four completion flags.
- Reviewed StepBar and completedThrough: evidence/personas/insights route to stages 7/8/9, with segment completion at 6 and legacy evidence gating preserved.
- D-301/D-259: `load_package` validates the file through the producer-owned `app.evidence.package.EvidencePackage`, then builds the stage-8 read projection. Numeric/null polarity, null novelty/quotes/metrics/quality are accepted. Cards, concept citations, opportunity maps and insight bars preserve missing values; unpositioned map rows remain in the context table rather than becoming zero-valued points.
- Real stage-7 packages have no top-level `run` or `projectContext`. The stage-8 fixture now matches the producer's complete nested key sets, including params and nullable distance fields. The reader obtains the generation ID from version-local session evidence metadata; completion caching includes that session file so an otherwise identical evidence rerun invalidates persona completion.
- Added `backend/tests/persona/test_package_contract.py`: runs the real offline stage-5 → stage-6 → stage-7 integration path via HTTP and worker dispatch, compares every nested object's key set with the stage-8 fixture, loads the resulting package and generates every persona card using FakeBackend. Additional assertions cover nullable values, invalid schema rejection, generation changes, completion-cache invalidation, map/bar output and null concept quotes. The fake tag input includes varying polarity and an artifact so counter-evidence and artifact object shapes are exercised in real producer output.
- D-316: restart options now include `8단계` / `stage8`; creating it opens `/pipeline/personas`. Added an interaction regression.
- Evidence's `페르소나 만들기` button reads version-local persona status, starts generation for an empty result unless already running/paused, then navigates to `/pipeline/personas`. Existing result cards are opened without regeneration. Existing mutation locking, read-only protection and error display apply. Added tests for empty/existing/running/failed states, duplicate clicks and errors.
- Corrected incoming stage-7 TypeScript quote nullability and test fixture typing discovered by supplementary type checking.

## Verification

- Full backend: `backend/.venv/bin/python -m pytest backend/tests -q` — **2,320 passed, 3 deselected, 2 warnings**, exit 0, 385.62 seconds (log `/tmp/task-T17-backend.log`). Warnings: existing Pydantic class-config deprecation and joblib physical-core detection fallback. The exact requested command was used.
- Focused backend against the final completion-cache adjustment (made while the full suite was running): 45 passed (`test_package_contract.py` and `test_session_completion.py`).
- Frontend: 64 files / 691 tests passed; rerun after TypeScript corrections also passed.
- Frontend lint: passed, including rerun after the corrections.
- TypeScript: `frontend/node_modules/.bin/tsc --noEmit --incremental false -p frontend/tsconfig.json` passed.
- `git diff --check`: passed.
- Conflict-marker verification: no matches in backend/frontend source (recursive grep excluding `.venv`, `node_modules`, and `.next`; exit 1). The exact requested unrestricted grep completed but found 9,325 matches exclusively inside those dependency/generated directories, including binaries and TypeScript's own conflict-marker parser. Those files were not edited.
- No next build, commits, branch operations, reset, abort, staging or subagents.

## Concerns / controller handoff

The requested `git diff --name-only --diff-filter=U` check still lists the six originally conflicted files. Editing removes textual conflicts but does not clear Git index stages. The task explicitly permits only file edits and read-only Git operations, and this worktree's Git metadata is read-only. Accordingly, the controller must stage these six resolved files (and review/stage the other T17 changes) before completing its merge. No Git metadata write was attempted.

The existing controller edit to `docs/development/dcx2-stage8/decision-log.md` was preserved.
