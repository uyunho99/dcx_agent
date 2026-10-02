# T12 report — completed

Date: 2026-10-02

Implemented frontend API clients, stage-8 types and pure display helpers. The API table in `task-T12-brief.md` is the authority for methods, paths and request bodies; no backend router implementation was used as a substitute contract.

## Files

- `frontend/src/lib/api/persona.ts`: run, status, cards, individual card, retry, map and tree. Uses `contextRequest`, `versionQuery` and encoded session/item IDs; retry sends `{run}` separately from worker `{runId}` responses.
- `frontend/src/lib/api/insight.ts`: run, root read, singular `/concept/{id}`, chat, revert and PUT confirm. Includes `/known/{sid}/suggestions` and an explicit suggestion-add helper sending `from: 'prev_session'`. No automatic suggestion writes. Existing known client remains unchanged.
- `frontend/src/lib/types.ts`: appended Persona*/Insight* request, response, grade, map, prescription, scope, revision, concept, journey and suggestion types. Chat results are a discriminated union preserving the exact Korean rejection message.
- `frontend/src/components/persona/personaView.ts`: the five helpers listed in the brief, without React components or backend metric recalculation.
- `frontend/src/components/persona/personaView.test.ts`: 29 offline tests covering display boundaries and API wire behavior.

## Helper conventions for downstream components

- `gradeLabel`: observed → `{text: '관측', shape: 'circle'}`, inferred → `{text: '추론', shape: 'triangle'}`, speculated → `{text: '추측', shape: 'cross'}`; null → `{text: '근거 부족', shape: null}`.
- `sortContexts(rows, key, dir)`: accepts readonly rows with `context_id` and scalar sort keys; returns a new array. Primary sort follows `asc`/`desc`, ties use ascending context ID, and identical IDs/values retain input order. Missing/nonfinite metrics remain last in either direction. Rows at overlapping coordinates are retained.
- `foldColumns(n)`: returns `{rows, columns}`. Counts 0–4 yield one row and n columns; 5–8 yield two rows of four; 9–10 yield two rows of five. Noninteger/out-of-range counts throw `RangeError`.
- `zoneName`: A Exciting, B Experiencing, C Competitive, D Forgiven, E Dangling, F At-risk; returns the name without the letter prefix.
- `cxCounts`: counts each journey row's `cx_4d`; always returns 정신적 · 물리적 · 문화적 · 시스템, including zero counts.

## Validation

1. Created `personaView.test.ts` before implementation.
2. RED: `npm --prefix frontend test -- persona` exited 1 because `./personaView` did not exist.
3. GREEN: the same command passed all 29 tests after implementation.
4. Refactored shared known endpoint path construction.
5. Ran `npm --prefix frontend test` once: **53 files, 496 tests passed**.
6. Ran `npm --prefix frontend run lint` once: **passed**, no lint diagnostics.
7. Additional `tsc --noEmit --incremental false` initially caught empty-array generic inference for `sortContexts([], 'context_id', 'asc')`. Corrected its type signature, then reran the type check (**passed**) and the targeted persona tests (**29 passed**). This final change only affects the TypeScript signature; the full suite and lint were not repeated.
8. `git diff --check` passed. `next build` was skipped as requested.

## Concerns / integration notes

- The table does not fix nested card, trace, tree, history-entry, radar or bar-entry serialization. Those portions remain `unknown` or open records rather than invented router-specific fields. T11/T13 should refine these nested types when their serialization contract is explicit. Endpoint methods, paths and request bodies are covered by offline fetch tests; live backend integration is not part of this task.
- Vitest emits Node's existing `DEP0205` warning about `module.register()`; it does not fail tests.
- No backend files, React components, routes or existing known client were changed by this task. Concurrent backend work was left untouched. No subagents, git staging or commits were used.
