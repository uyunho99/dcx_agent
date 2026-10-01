Status: COMPLETE

Fixed Q3: CoveragePanel displays the backend `previous` snapshot only while coverage is loading. Previous metrics, evidence counts, source/weighting labels, and missing-query rows remain visible at reduced opacity; the panel has `aria-busy=true`. The loading announcement uses the current request's source, and refresh remains disabled. Terminal responses use current values, never the previous snapshot.

Files changed:
- frontend/src/components/keywords/CoveragePanel.tsx
- frontend/src/components/keywords/CoveragePanel.test.ts
- frontend/src/lib/types.ts (added the optional typed previous snapshot)
- .superpowers/sdd/03-plan/qfix-fe-report.md

Verification:
- Tests written before the implementation, using the backend snapshot shape without status/progress metadata.
- RED: `npm --prefix frontend test -- --run` — 2 failed, 292 passed. Both failures reproduced missing previous values (autocomplete retention and searchad-to-autocomplete refresh).
- GREEN: `npm --prefix frontend test -- --run` — 44 test files passed, 294 tests passed.
- `npm --prefix frontend run lint` — passed.
- Regression coverage includes dimming/busy semantics, retained missing rows and evidence counts, provider-specific labels, current loading copy, disabled refresh, and ignoring previous values after loading. Existing first-load and polling tests also pass.

Backend rounds.py was read only. No backend files edited and no commit created. Verification used rendered component markup in Vitest; no live browser QA rerun was performed.
