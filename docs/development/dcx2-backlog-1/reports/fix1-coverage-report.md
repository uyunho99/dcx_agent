Status: COMPLETE

Applied coverage review round 1 within the allowed scope. No commit created.

Changes
- Non-refresh coverage recalculates every metric and llm_only badges from saved humanQueries/humanAxes and the current approved LLM keywords. Both autocomplete and searchad R2 re-commit regressions verify that missing_top and weighted coverage change without fetching or classification.
- Persist humanQueries with loading/classifying before classification. Fetching, classification, and completion carry updatedAt. A 30-second classification heartbeat keeps active work fresh; stale detection uses updatedAt with startedAt fallback and retains the two-minute inactivity limit. Ownership/version checks protect phase writes and final results. Completion also uses the latest approved set.
- Omit empty/whitespace-only bk autocomplete seeds.
- Loading copy distinguishes autocomplete from searchad and first-load headlines say '커버리지를 계산하는 중입니다'. Unavailable metrics hide retained percentages and show 계산 불가.
- R3 coverage_signals explicitly label '자동완성 순위' or '월간 검색수'. Limit the R3 waiting message to R2/R3.

TDD — RED
Before implementation:
- backend/.venv/bin/python -m pytest backend/tests/keywords/test_rounds_api.py -q: 7 failed, 60 passed. Failures covered old-failure recovery, both re-commit sources, classification persistence/freshness, empty bk, and both R3 labels. Log: /tmp/coverage-red-backend.log.
- npm --prefix frontend test -- --run src/components/keywords/CoveragePanel.test.ts: 4 failed, 15 passed. Source-aware first-load headlines and stale metrics failed. Log: /tmp/coverage-red-frontend.log.
- During GREEN, corrected the re-commit fixture to advance both round.gen and job.gen, supplied deterministic queries for old-failure recovery, and updated the expected empty-bk seed count from 21 to 20. Added a deterministic heartbeat regression spanning 150 simulated seconds without sleeps or network.

Verification — GREEN
- backend/.venv/bin/python -m pytest backend/tests/keywords/test_rounds_api.py -q: 68 passed.
- backend/.venv/bin/python -m pytest backend/tests -q: 1395 passed, 1 deselected, 2 warnings. Final log: /tmp/coverage-full-backend-final.log.
- npm --prefix frontend test -- --run: 44 files, 285 tests passed. Log: /tmp/coverage-full-frontend.log.
- npm --prefix frontend run lint: passed. Log: /tmp/coverage-lint.log.
- git diff --check on owned files: passed.
- The first full backend run had one unrelated failure in context/test_api.py::test_legacy_full_save_still_overwrites while other jobs edited the workspace. That test passed on isolated rerun; the subsequent full run passed. No edits were made to that test or its implementation.
- Tests use fake adapters/LLM responses and mocked fetch; coverage re-commit tests explicitly fail on any fetch/classification attempt. No network is required.

Scope and interpretations
- Edited backend/app/keywords/rounds.py, backend/tests/keywords/test_rounds_api.py, frontend/src/components/keywords/CoveragePanel.tsx, its existing CoveragePanel.test.ts, frontend/src/app/pipeline/keywords/page.tsx, and this requested report. The allowed router file needed no change because GET already delegates stale interpretation to coverage_status.
- 'Only refresh refetches' means an existing human-query cache is reused unless refresh=true. A failed attempt without cached queries may fetch again, restoring the requested old-failure recovery behavior. An interrupted fetch without cached queries remains unavailable until explicit refresh.
- Interruption is represented by status=unavailable with error.kind=interrupted; the unavailable metric rendering covers that API state.
- A heartbeat preserves genuine slow classification while still expiring abandoned jobs, rather than exempting classification from stale detection.
- All other parallel-job files were left untouched. Existing Pydantic deprecation and joblib CPU-detection warnings remain.
