Status: COMPLETE

Applied R-207 coverage fixes from `.superpowers/sdd/03-plan/rfix-coverage.md`, addressing Codex review findings 1–2 and gstack findings 1–3.

Files edited by this job:
- `backend/app/keywords/rounds.py`
- `backend/app/external/naver_autocomplete.py`
- `backend/tests/keywords/test_rounds_api.py`
- `backend/tests/keywords/test_autocomplete.py`
- This required report.

Changes:
- Autocomplete accepts optional `on_progress`, called after each successful or failed seed. Callback exceptions stop collection and close owned clients. Coverage callbacks use the same loading/startedAt ownership checks as publication.
- A 30-second heartbeat now covers SearchAd fetching, autocomplete fetching, and classification, and is stopped/joined on exit.
- R3 admission and regeneration check projected coverage inside the session mutation lock. Loading returns HTTP 409 with the exact message `커버리지를 받는 중입니다. 끝나면 R3를 만들 수 있습니다.` Connected, unavailable, unconnected, and stale loading projected as unavailable still permit R3.
- R3 saves a replacement coverage snapshot under that same lock; `_inputs` uses that snapshot even if coverage refreshes before the queued round runs. Regeneration replaces the prior snapshot.
- Entering loading moves humanQueries, humanAxes, all coverage metrics, source, and weighting into display-only `previous`; active fields and old errors are cleared. Cached recomputation ignores `previous`. A refresh older than two minutes followed by R2 re-commit remains unavailable until that refresh succeeds.

TDD RED — before production edits:
Command: `backend/.venv/bin/python -m pytest backend/tests/keywords -q -k review`

Recorded output:
```text
=========================== short test summary info ============================
FAILED backend/tests/keywords/test_autocomplete.py::test_review_progress_after_success_and_failure
FAILED backend/tests/keywords/test_autocomplete.py::test_review_progress_can_stop_superseded_fetch
FAILED backend/tests/keywords/test_rounds_api.py::test_review_r3_loading_gate[False]
FAILED backend/tests/keywords/test_rounds_api.py::test_review_r3_loading_gate[True]
FAILED backend/tests/keywords/test_rounds_api.py::test_review_r3_terminal_snapshot[connected]
FAILED backend/tests/keywords/test_rounds_api.py::test_review_r3_terminal_snapshot[unavailable]
FAILED backend/tests/keywords/test_rounds_api.py::test_review_r3_terminal_snapshot[unconnected]
FAILED backend/tests/keywords/test_rounds_api.py::test_review_r3_terminal_snapshot[stale]
FAILED backend/tests/keywords/test_rounds_api.py::test_review_stale_refresh_recommit_never_reuses_previous
FAILED backend/tests/keywords/test_rounds_api.py::test_review_slow_autocomplete_fetch_keeps_loading
FAILED backend/tests/keywords/test_rounds_api.py::test_review_searchad_fetch_heartbeat
11 failed, 233 deselected, 1 warning in 3.37s
```

Observed failures included: missing on_progress parameter; R3 returning 200 instead of 409; queued R3 using later refresh signals; old cache fields remaining active; unavailable appearing during the simulated 21 × 9-second fetch plus 20 one-second pauses; no heartbeat before SearchAd fetching.

During GREEN validation, corrected the re-commit test setup to mark R2 uncommitted before re-committing (the API correctly rejects an already committed round), and expanded terminal snapshot tests to cover regeneration too. Existing autocomplete test doubles now accept the optional callback.

GREEN:
```text
$ backend/.venv/bin/python -m pytest backend/tests/keywords -q
248 passed, 1 warning in 13.66s

$ backend/.venv/bin/python -m pytest backend/tests -q
1430 passed, 1 deselected, 2 warnings in 139.28s (0:02:19)
```

Tests used fake backends, MockTransport, simulated clocks, and controlled heartbeat threads; no external network was used. The full suite retained its network guard. Warnings concerned Pydantic configuration deprecation and physical-core detection. The configured perf exclusion accounts for the deselected test.

Scoped `git diff --check` passed. No frontend edits and no commits. Concurrent changes to sessions.py, stale.py, and context tests were left untouched; full-suite results reflect the shared working tree at execution time.
