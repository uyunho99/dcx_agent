Status: COMPLETE

- Isolated completion fields: any computation exception yields false for that field while preserving session/version reads and other completion evidence.
- Added offline backend regressions for invalid collectionId, SQLite without a runs table, missing cluster files, and malformed milestones.
- Made unavailable/failed coverage interpretation source-aware, retaining the exact autocomplete wording and using the requested searchad wording; added Vitest coverage for both sources and statuses.
- TDD verified before implementation: backend regressions failed (9 cases); frontend regressions failed (3 cases).
- `backend/.venv/bin/python -m pytest backend/tests -q`: PASS, 1404 passed, 1 deselected, 2 warnings.
- `npm --prefix frontend test -- --run`: PASS, 288 tests across 44 files.
- `npm --prefix frontend run lint`: PASS.
- `git diff --check`: PASS. No commit made.
