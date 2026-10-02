# Merge review 1: f35a4a1 (bundle ② stage 7 → bundle ③ stage 8)

- Scope: `git show --cc f35a4a1`, `git diff 4ab206c f35a4a1`, and `git diff 3ebfb1e f35a4a1` for the conflict files, the shared files and the T17 changes. This was a read-only review.
- Parents: ③ `4ab206c`, ② `3ebfb1e`, base `0bc13cf`.
- Test runs (all pass):
  - `pytest backend/tests/persona backend/tests/evidence backend/tests/context`: 795 passed, 1 deselected
  - `pytest backend/tests/llm`: 30 passed
  - `npm --prefix frontend test`: 691 passed in 64 files
  - `tsc --noEmit`: clean
  - The worktree is still clean after the runs.

## Verdict

**Approve with one Important fix.** The merge lost no behaviour from either side and registered nothing twice. The contract test really uses bundle ②'s real output. The open gap is in stage 8: it uses whatever `package.json` is on disk and never checks that stage 7 finished and is still current.

Counts: Critical 0 · Important 1 · Minor 6

## Lost behaviour and double registration: none found

- **Worker kinds** (`backend/app/work/worker.py:122`): `KINDS` contains prep, judge, train, infer, monitor, segment, evidence, persona and insight. All 9 are present, with one handler each.
- **Routers** (`backend/app/main.py:22-23, 62-63`): `stage8` and `evidence` are each included once. Across `stage8`, `evidence` and `personas` the method+path pairs don't collide (checked by introspection). `/evidence/*` has 7 routes and `/persona/*` plus `/insight/*` have 13.
- **Completion flags** (`backend/app/routers/sessions.py:117-127`): personaDone, insightDone and evidenceDone are all computed. The order of the 4 dict assertions in `test_session_completion.py` doesn't matter.
- **Fake echo builders** (`backend/app/llm/fake.py:27-38`): there is one table of builders. It holds ② `BUILDERS` (evidence.queries, tag, novelty), `segment.dims → _segment_echo`, and the 6 persona/insight tasks → `_persona_echo`. All 10 `*.echo.json` fixtures have a builder. The path choice (`echo.exists() and (segment.dims or attachments)`) behaves the same as ②'s narrower rule, because the only echo files are these 10.
- **Types** (`frontend/src/lib/types.ts:227-371`): the stage-8 block (Persona*, Insight*) and the stage-7 block (Evidence*) are both complete. The merge made two type changes of its own, both safe and both passing tsc: `PersonaMapPoint.i/s/odi/zone` and `EvidenceItemView.quote` became nullable.
- **versions.py**: ②'s `_restart(stage<=7)` keeps the evidenceDone pop, `evidence={'status':'none'}` and the `undifferentiated_candidate` clear. ③'s `stage<=8` persona/insight reset is kept too. `compare('stage7')` from ② is present next to ③'s `stage8` compare. `test_versions_stage8.py` now also asserts that segmentDone and evidenceDone are kept or dropped correctly for each restart stage.
- **StepBar / StageVersion / completedThrough**:
  - In StepBar, 근거 탐색 links to `/pipeline/evidence` behind the `derivedRef` gate at index 7, and 인사이트 links to `/pipeline/insights`.
  - `routes` now covers stages 0-8, so stage 8 opens `personas`. Before the merge, ③ mapped index 7 to `personas`.
  - completedThrough checks 9, then 8, then 7, then 6.
- **Files ② never touched**: insights page, `registry.py`, `known.py`, ChatPanel and `errors.ts` differ only by ③'s own changes. I compared base→② numstat to confirm none of them was dropped.
- **Merge-side test edits**: the tests that used to change `package['run']` now change `session.evidence.run` or `params`. That matches the new rule that the generation comes from session.json, and it doesn't weaken the tests.

## Contract: stage-7 output vs stage-8 consumption (design §2.4)

- `persona/package.py:146-150` first validates with ②'s own `EvidencePackage` (`extra='forbid'`, Literal enums). It then projects into ③'s permissive `Package`.
- `run` is no longer read from the package. It comes from `session.json` → `evidence.run`, and `session.json` was added to the `_persona_sources_match` stamp tuple (`sessions.py:94`).
- **Field names**: they match §2.4 at every level. `object_keys(synthetic) == object_keys(real)` checks this structurally.
- **Nullability**: ③ used to have `polarity: str` and required `quote`, I/S/ODI and quality. These are now `float | None` and `Quote | None` as ② produces them. The downstream null paths are handled:
  - `cards.py:148`, `concepts.py:133-134`: null quote
  - `opportunity.py:46, 58-60, 84-85`: null metrics, with zone=None and star=False
  - `insights.py:51-60`: odi=None bars and mean
  - `OpportunityMap.tsx:43`, `personaView.ts:40`: null points and zone in the UI
- **Is the contract test using ②'s real output?** Yes. `test_package_contract.py` runs ②'s real pipeline end to end: `/evidence/run`, then the worker, then `assemble`, then `package.json`. It runs offline through ②'s `offline_worker`, `bind_backend` and `fake_evidence_backend`. It then loads the result with `load_package`, generates cards for every Persona, builds the map, and checks personaDone and stale detection. It also mutates the real file into the nullable shapes.
  - The limits of the test are listed under Minor 6.

## Findings

### Important

**I1. Stage 8 consumes `package.json` without checking that stage 7 is done and current.**
- Where:
  - `backend/app/routers/stage8.py:76-81` (`_package`) and `:121-130` (`start_persona`) only check that the file exists.
  - `backend/app/persona/pipeline.py:203-232` (`run`) and `backend/app/routers/sessions.py:85-97` (`persona_done`) never read `data['evidence']['status']` or `stale['stage7']`.
  - Meanwhile ② leaves an old `package.json` on disk in several states:
    - segment rerun reset: `backend/app/segment/pipeline.py:66-70` sets `evidence={'status':'stale'}` and doesn't delete the package
    - non-fresh evidence resume: `evidence/pipeline.py:213-218`
    - skip leaving `partial`: `evidence/pipeline.py:679-686` calls `_assemble` while the status is `partial`
- Scenario A:
  1. Stage 6 is rerun in the same version. Evidence becomes `stale` and evidenceDone is dropped, but the old package stays.
  2. The user confirms the redrafted Personas and Contexts with the same IDs, names and actions. `_confirmed_matches` becomes True again, and the package digest and `evidence.run` haven't changed.
  3. Result: `mark_stale_if_changed` returns False, `/persona/status` reports `evidence_required: false`, and personaDone flips back to True. Old cards built on the previous segment's document assignments show as current. `POST /persona/run` would also build new cards from that stale stage-7 output.
- Scenario B:
  1. A Context fails, and the user skips another one, which leaves the status `partial`. `package.json` gets written anyway.
  2. Result: `POST /persona/run` succeeds, so personaDone can be True while evidenceDone is False.
  3. Only the frontend 페르소나 만들기 button is gated on `status==='done'`. The API and the Persona screen's own run button are not.
- Fix: add one predicate, `evidence_ready(data) = data.evidence.status == 'done' and 'stage7' not in data.stale`.
  - In `_package` / `start_persona` / `retry_persona`, raise 409 `evidence_required` when it fails.
  - Return `evidence_required=True` in `persona_status`, and make `mark_stale_if_changed` / `persona_done` treat a failure as stale or not-done.
  - Or, as a simpler addition, unlink `evidence/package.json` in the segment `reset` branch.
  - Add a test that covers the segment rerun followed by an identical re-confirm.

### Minor

**M1. A package that fails validation causes HTTP 500, and the docstring is now wrong.**
- Where: `backend/app/persona/package.py:3`, `:146`.
- `extra='forbid'` plus the Literals now reject any extra or legacy key. Examples are the old ③ fixture keys `run` and `projectContext`, or `polarity:'negative'`, which may sit in stage-8 QA sessions generated before the merge.
- `pydantic.ValidationError` isn't caught at `stage8.py:78, 96, 146` or `pipeline.py:114`. Only `PackageMissing` and `sqlite3.Error` are caught, so `/persona/{sid}/status`, `/cards` and `/run` return 500.
- The module docstring still says "Unknown fields are retained … forward compatibility", and `test_package.py` dropped that assertion.
- Fix: in `load_package`, wrap ValidationError as `PackageInvalid(PackageMissing)` or as a 409 `evidence_required` saying 근거 탐색을 다시 실행하세요, and update the docstring.

**M2. `concepts.py:178` has a dead fallback.**
- `getattr(package, 'projectContext', {})` can never be set now that the producer model forbids extras. The session value is always used, so this is harmless.
- Fix: remove the fallback, or add a comment.

**M3. Null ODI bars are drawn as 0.**
- Where: `frontend/src/components/persona/InsightScreen.tsx:92`.
- The backend now sends `{'odi': None}` for insights with no measured Context (`insights.py:55`). `number(row.odi ?? row.value) ?? 0` draws that as a 0 bar, which can't be told apart from a real 0.
- Fix: leave such bars out, or render them as "—" the way `formatMetric` does.

**M4. A null-quote trace shows an empty location and no 인용 미확인 mark.**
- Where: `frontend/src/components/persona/PersonaScreen.tsx:108-109`.
- When `ref.quote` is null, `record(null)` gives `{}`. The location renders as empty labels, and `quote.verified === false` is false, so the mark is missing.
- The grade is still downgraded to 추론 (`EvidenceRef.verified=False`), so the trace row doesn't match the grade.
- Fix: when `ref.quote == null`, render "인용 없음 · 추론".

**M5. Evidence and persona runs can be launched at the same time (TOCTOU race).**
- Where: `backend/app/work/runner.py:29-33`. The DB-level exclusion covers only `segment` and `evidence`.
- The evidence router checks `active` under `sessions.locked` and then calls `runner.start` after releasing the lock (`routers/evidence.py:56-64`). The stage-8 launch uses a separate `.stage8-launch.lock` (`stage8.py:110-117`).
- So two near-simultaneous POSTs, `/evidence/run` and `/persona/run`, can both register. Persona's `Source.check` then detects the package change and fails the run as stale. That is safe but wasteful.
- Fix: add `persona` and `insight` to the conflict set in `runner.start` alongside `segment` and `evidence`.

**M6. The contract test has coverage gaps.** The test is sound, but these parts aren't covered (`backend/tests/persona/test_package_contract.py`):
- `object_keys` compares key sets only. Value types and nullability are checked only through the hand-written `nullable` mutation, and only on the first evidence row of the first Context. The test doesn't produce rows with null polarity or quote straight from ②.
- Cards are made by calling `generate_card` directly. The real ② package never goes through `POST /persona/run`, the `persona` worker or `insight_pipeline`. `test_integration.py` covers those, but only with the synthetic `make_package`.
- I1 isn't covered.
- Fix: run `/persona/run` and `/insight/{sid}/run` (derive) once on the real ② package. Also add a test where evidence is stale and the package is unchanged.

## Other notes (no action needed)

- In `fake.py`, a builder exception for `evidence.*` now becomes `failure('schema', …)` instead of being raised. In ② it was raised. This is consistent with ③'s persona echo and only affects offline QA.
- On 페르소나 만들기 (`EvidenceScreen.tsx:195-199`), stage 8 is started only when there are no persona cards and nothing is running or paused. Otherwise the button only navigates, so stale cards are handled by the Persona screen. A start error shows on screen and blocks navigation, and this is tested.
- The 8단계부터 다시 option is backed by `create_version` (`last_stage = max(8, …)`) and `_restart(stage<=8)`. Its test is `StageVersion.test.ts`.
