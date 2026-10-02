# T15 report

Status: implemented (D-305 / D-306 / D-217).

## Delivered

- `/pipeline/insights` selects the new screen when the selected session has `prep.derivedRef`; otherwise it renders the preserved old insights screen. `/insights` redirects to `/pipeline/insights`.
- New `InsightScreen`: responsive 2/3 cards and 1/3 chat/revisions layout; titles, pain points, Context chips, server radar values, Known badges, explicit confirm checkboxes, Opportunity bars and mean line.
- Selected concept: synthetic persona with red `🔴 합성값`, basis, evidence quote/channel/location/Context ID, JOURNEY, all four CX counts, and constraint verdict symbols/text.
- Explicit derive/concept actions, bounded result polling, loading/error/retry states and exact zero-insights copy. Server default-target metadata selects the initial recommended insight when supplied.
- Chat target selector, exact failure copy with no local revision replacement or reload on failed requests, historical snapshots, and server-backed revert followed by reload. Confirmation writes server IDs and refreshes session completion state.
- Sidebar insight link and completion precedence: insightDone → 9, personaDone → 8, segmentDone → 6.
- Collapsed previous-session suggestions loaded using the existing API client. Addition occurs only through the user's button click and POSTs `from: 'prev_session'`; readonly/busy states prevent writes, and successful additions update the drawer and callback.
- Shared ChatPanel now honors its existing readonly prop for text entry, send button, and send handler.

## TDD and checks

1. Wrote tests first; `npm --prefix frontend test -- insight known` failed because the new action module did not yet exist.
2. Implemented; the same command passed, then added concept rendering, API origin, and actual route-branch tests.
3. Final `npm --prefix frontend test -- insight known`: **15 passed**, 3 files.
4. Related regression run `npm --prefix frontend test -- insight known completedThrough`: **106 passed**, 4 files.
5. Ran `npm --prefix frontend test` **once**: 535 tests passed, 1 failed, plus 1 suite failed to load. The failed assertion was the old expectation that the insight sidebar link remained disabled; it was updated to the new requirement and passed in the related regression run. The load failure was the parallel worker's then-missing PersonaScreen implementation; once available, its targeted suite passed **10/10**. The complete suite was not rerun, per the once-only instruction.
6. Ran `npm --prefix frontend run lint` **once**: 0 errors, 1 warning for an unused PersonaCard import in the parallel worker's PersonaScreen.tsx at the time of the run. No T15 lint diagnostics.
7. Final `tsc --noEmit --project frontend/tsconfig.json`: passed.
8. No next build, git add, commit, subagents, backend edits, or edits to the parallel worker's PersonaScreen/personas route.

## Concerns / limits

- Tests use mocked API calls and server-rendered component assertions; no live browser/backend end-to-end verification was performed. T11 API integration remains to be validated with the assembled backend.
- The one full-suite run was not green for the two causes documented above; both affected suites subsequently passed targeted runs.
- Async generation is observed through the contracted GET insight revision endpoint, with a six-minute bounded polling window and explicit retry feedback. There is no insight-status endpoint in the supplied contract.
