Status: COMPLETE

- M4: Loading coverage records retain the expected source using SearchAd's credential checks; refresh selects the current source while keeping old metrics in `previous`.
- M3: Repeat R3 requests return the existing running job before the coverage-loading 409 gate, including regenerate requests; the admitted snapshot stays unchanged.
- M5: Progress persistence errors log a warning and allow fetching to continue. Superseded workers still stop without classification or overwriting the replacement result.
- Changed only `backend/app/keywords/rounds.py`, `backend/tests/keywords/test_rounds_api.py`, and this report. No commits.

Tests (offline fixtures and network guards):
- RED, before implementation: focused `-k 'review2 or review_stale_refresh'` run produced 9 expected failures and 1 passing supersession guard.
- GREEN: `PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/python -m pytest backend/tests/keywords/test_rounds_api.py -q -p no:cacheprovider` — 90 passed, 1 warning.
- Full suite: `PYTHONDONTWRITEBYTECODE=1 backend/.venv/bin/python -m pytest backend/tests -q -p no:cacheprovider` — final run 1447 passed, 1 deselected, 2 warnings (138.65s). Warnings concern Pydantic configuration deprecation and joblib physical-core detection.
- Initial full-suite run overlapped the other job's edits: 1440 passed, 6 failures in completion/stale-state tests. Reran after those implementation files changed; final run passed without editing them.
- `git diff --check -- backend/app/keywords/rounds.py backend/tests/keywords/test_rounds_api.py` passed.
