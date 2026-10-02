# T15 report

Status: implemented; targeted RED → GREEN verified. Full-suite verification is blocked by failures outside T15 ownership.

## Changes

- `frontend/src/components/segment/ContextLayer.tsx`: flagged Context cards show the exact warning Badge `새 Context 후보 — 원문 3건` inside a native, keyboard-accessible expandable details control. No create action. Loading, retryable read errors, empty results, and unmount protection are included.
- Data choice: `SegmentContext` / the 6-C contexts response has no `undifferentiated` field. The first expansion calls `getEvidenceContext(sid, contextId, 'all', version)`; it reads the first three `undifferentiated` entries and resolves document IDs to `text` through the response's `items`, `counter`, and `rare` arrays. Unmatched strings are displayed verbatim (supporting text-valued entries). Reads are deduplicated while pending and cached for the mounted card; session/version/context and segment-run changes reset the card. No evidence API/type changes were made.
- `frontend/src/components/segment/SegmentScreen.tsx`: the existing button navigates to `/pipeline/evidence`; it does not start evidence on screen 6. It becomes available after stage 6 is done, nonzero confirmation totals all match, results are loaded, and the screen has no pending edits or blocking state. Passes sid/version to Context cards. The old always-disabled `canStartEvidence` helper is no longer used by this screen; its file was outside the assigned implementation scope and remains unchanged.
- `frontend/src/app/pipeline/labeling/page.tsx`: reads `getEvidenceStatus(sid, version)` independently of label overview and displays the exact info Banner `7단계에서 무관 판정 N건 — 4단계 재점검 참고` only for positive finite numeric `stage7.irrelevant`. Missing/zero reports and unavailable evidence APIs do not disrupt legacy labeling. No automatic re-judging or new mutation was added.
- Tests: new segment T15 tests cover lazy three-source expansion, read reuse, flag absence, and navigation without starting a run. Labeling tests cover the info banner and legacy sessions with absent/zero/unavailable evidence. Existing SegmentScreen tests in clustering/page.test.ts were updated for the new disabled reason and loading guard.

## Verification

1. `npm --prefix frontend test -- segment labeling` before implementation: FAIL, exactly the three addition tests failed; 36 passed.
2. Same command after implementation: PASS, 39 tests / 4 files.
3. `npm --prefix frontend test` (once): 502 passed, 1 test failed, plus 1 suite failed to load; 53 test files passed / 2 failed.
   - `components/evidence/evidenceScreen.test.ts`: missing `./EvidenceScreen` module during the parallel worker's development.
   - `components/evidence/evidenceView.test.ts`: `slices backend Unicode code-point offsets after an emoji` failed (UTF-16 versus code-point offset mismatch).
   - All 44 existing clustering tests passed, as did all T15 tests.
4. `npm --prefix frontend run lint` (once): PASS.
5. Next build intentionally skipped. No git add or commit; no subagents. Backend, evidence implementation/tests, StepBar, and completedThrough were not modified by this task.

## Concerns / integration follow-up

- Full-suite failures above belong to the parallel evidence work and remain for its owner to resolve.
- The declared `undifferentiated: string[]` contract does not distinguish document IDs from literal texts. IDs must have corresponding text in `items`/`counter`/`rare` to show source text; an unmatched ID is displayed verbatim. Integration should verify the backend includes all three candidate texts in the context response.
- Starting the evidence run is owned by the destination screen and was not implemented or verified here; this task verifies navigation only, as requested.
