# T13 report

Status: complete.

Implemented the seven API table routes in `frontend/src/lib/api/evidence.ts` using `contextRequest`, encoded session/entity IDs, and `versionQuery`. Context reads default to `tab=all`; refresh-new and skip send exactly `{run}`; run accepts `{fresh?, contexts?}` and returns the worker `runId` separately from the generation `run`.

Added Evidence-prefixed wire types to `frontend/src/lib/types.ts`, including status rows, queries, item views, package items, package envelope, requests, responses, and all six contracted error kinds. Shared request error handling remains in use.

Added pure display helpers in `frontend/src/components/evidence/evidenceView.ts`: `rowBadge`, `canBuildPersona`, `locationLabel`, `highlight`, and `excludedMessage`. Korean copy matches the request. Highlight ranges are half-open, require finite integer offsets within the supplied text, and omit empty surrounding segments. Invalid/null ranges preserve the original text in one unmarked segment.

Validation:

- RED: wrote `evidenceView.test.ts` first, including offline API tests following the segment suite; `npm --prefix frontend test -- evidence` exited 1 because the implementation module did not exist.
- GREEN: implemented the modules; the same evidence command passed all 29 tests.
- Refactor: reused `EvidenceContextStatus` for the persona gate input and reviewed shared path helpers/type boundaries.
- `npm --prefix frontend test`: run once after implementation/refactor; 53 files, 496 tests passed.
- `npm --prefix frontend run lint`: run once; passed with no findings.
- `./frontend/node_modules/.bin/tsc --project frontend/tsconfig.json --noEmit --incremental false`: passed.
- `git diff --check`: passed.
- Next build intentionally skipped as requested. No git add/commit, backend edits, React components, or subagents.

Contract notes / concerns:

- The brief does not define nested fields for the context response's `context`, `artifacts`, or package `PersonaBlock`; these remain `Record<string, unknown>` rather than an invented backend schema. T12/T14 can refine them once those nested contracts are specified.
- Context states use the design's `queued/running/done/failed/skipped`; the overall state includes `partial` per the plan's failure rule. `canBuildPersona` implements the requested every-context predicate literally, including true for an empty context list; screen lifecycle gating belongs to T14.
- Quote offsets use JavaScript string indices. The API table does not specify Unicode code-point versus UTF-16 offset units; T12 integration should settle this for non-BMP text.
- The API suite is offline and validates the brief's contract, not the later backend router. Vitest emitted the existing Node `module.register()` deprecation warning; checks still passed.
