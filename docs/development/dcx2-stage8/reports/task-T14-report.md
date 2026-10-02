# T14 — Persona screen implementation report

Status: implemented; frontend verification passes. Backend/browser integration remains to be verified when T11 and the evidence route are available.

## Changes

- Added `frontend/src/components/persona/PersonaScreen.tsx`.
  - Whole-session map is the initial view; Persona card view has no embedded map.
  - Map point and Context-table card actions select the matching Persona and open CCM; shared hover/focus highlights and Context details accompany the map. The sortable Context table sits below the map.
  - Left Persona navigation groups confirmed identities by cluster and includes textual card status and FUTURE badges.
  - Header displays confirmed name/Desire/Goal and source document/author/Context counts. Missing counts are displayed as unknown, never fabricated.
  - Implements 8-A CCM, 8-B convergence with fixed `의도 ≠ 행동`, 8-C attributes with `근거 부족`, 8-D prescription checks and blocked copy, and the size-adapted hierarchy tree.
  - Evidence cells display source, location, original quote, the exact unverified-quote tooltip, and version-aware Known Insight addition.
  - Version-aware polling retrieves status, cards, map, tree, and confirmed segment identities. Partial result reads recover on later polls. Mutations are locked while running/pending/readonly; completion refreshes session metadata.
  - One primary action switches from `페르소나 만들기` to `인사이트 도출`. Failed cards retry with the current run ID. Missing-package responses display the exact empty-state copy and evidence navigation.
- Updated `frontend/src/app/pipeline/personas/page.tsx` using the same `prep.derivedRef && sid` branch rule as clustering. The legacy function body is unchanged; new screens remount by session/version and receive readonly/conflict state.
- Made a narrow supporting change to `frontend/src/components/versions/StageVersion.tsx`: derived Persona routes pass through the old historical-route gate. Without this change, the requested readonly Persona screen could never mount. Legacy and other routes retain their existing gate.
- Added `frontend/src/components/persona/PersonaScreen.test.ts` with 12 tests covering views, point-to-card interaction, table sorting, failed retry, missing package, legacy branching, historical route access, readonly guards, partial fetch recovery, exact copy, and evidence/Known Insight wiring.

## TDD and validation

1. Wrote screen tests before implementation. `npm --prefix frontend test -- persona` failed because `PersonaScreen` did not exist (the parallel insight worker also had a temporarily missing module).
2. Implemented the screen and route. Persona tests passed.
3. Added a historical-route regression test, confirmed it failed, then applied the narrow boundary fix.
4. `npm --prefix frontend test -- persona`: 5 files, 81 tests passed.
5. Ran `npm --prefix frontend test` once: 57 files, 548 tests passed.
6. Ran `npm --prefix frontend run lint` once: passed, no diagnostics.
7. TypeScript `--noEmit`: passed.
8. Strengthened the existing evidence test to assert the actual Known Insight request; final targeted run: all 12 T14 tests passed.

No Next build, git add, or commit was performed. No backend files or the other worker's listed files were edited. Tests use mocks and require no network or keys.

## Integration concerns

- At verification time, `backend/app/routers/stage8.py` and `/pipeline/evidence` were absent. The screen uses the specified persona API contract and evidence destination, but live end-to-end navigation/API behavior could not be checked.
- The published status response has no package-presence flag, and the shared API error helper discards machine error kinds. The exact no-package state is recognized when a result/read or run request returns the specified Korean missing-package message; an otherwise idle status alone cannot establish whether a package exists. T11 must preserve that message, or a future contract should expose package availability/error kind.
- Current generated-card serialization includes state/emotion/barrier and metrics, but does not populate keywords/artifacts. CCM renders provided values and uses `근거 부족` for absent fields; it does not invent them.
- Browser visual QA was not performed. Existing shared CCM/map/table components and static/interaction tests were reused; no new packages were installed.
