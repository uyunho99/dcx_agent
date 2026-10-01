Status: COMPLETE

Files changed by this task:
- `backend/app/routers/prep.py`: the successful endpoint reuse branch calls `clear_stale(sid, data['version'], 'stage3', already_locked=True)` after saving completion, under the existing session lock.
- `backend/tests/prep/test_reuse_clears_stale.py`: offline regression through real `POST /prep/s/run`, with implicit active version and explicit v2. Checks repeated reuse, persisted/session-API stale markers, downstream marker preservation, unchanged v1 snapshot, and no worker launch or additional embedding.
- `.superpowers/sdd/03-plan/qfix-prep-report.md`: this report.

RED/GREEN evidence:
- Before implementation: `backend/.venv/bin/python -m pytest backend/tests/prep/test_reuse_clears_stale.py -q` — 2 failed in 3.16s. Both returned successful reuse but failed because persisted `stale.stage3` remained.
- After implementation: same command — 2 passed, 1 warning in 4.53s. The test blocks socket connections and uses the fake embedder; no network is required.

Verification:
- Required command `backend/.venv/bin/python -m pytest backend/tests -q` — 1448 passed, 10 failed, 1 deselected, 2 warnings in 143.60s. Prep and stale-clear tests passed.
- All 10 failures were in concurrently edited keyword tests outside this brief: 3 `test_empty_results_are_successful_seeds` cases in `test_autocomplete.py` (empty results counted as unavailable/failed); 5 product-context cases in `test_coverage.py` (`compute` did not accept `bk`); 2 `test_qfix_autocomplete_empty_and_product_queries` cases in `test_rounds_api.py` (incomplete ProjectContext fixture). This full-suite run is not green; those files were left to their parallel owner.
- `git diff --check` passed. No commits made; no files outside the authorized implementation/test paths and requested report were edited by this task.
