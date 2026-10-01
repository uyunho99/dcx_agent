Status: COMPLETE

Implemented browser-QA coverage fixes Q1 and Q2.

- Q1: Valid autocomplete responses with zero suggestions succeed and contribute no queries. Only request/parse errors count toward failedSeeds. All-empty successful responses persist connected coverage with zero human queries and m1=None; mixed empty/error responses remain connected. All-error responses remain unavailable. Existing no-seeds behavior is preserved.
- Q2: Rank mode excludes queries whose normalized key equals the product bk before classification, persistence, and metric computation. Matching also tries the normalized query with bk removed, retaining existing bidirectional partial matching. Cached recomputation applies the same filtering. Searchad/volume metrics retain their existing behavior.

Files edited:
- backend/app/external/naver_autocomplete.py
- backend/app/keywords/coverage.py
- backend/app/keywords/rounds.py
- backend/tests/keywords/test_autocomplete.py
- backend/tests/keywords/test_coverage.py
- backend/tests/keywords/test_rounds_api.py
- This required report.

TDD evidence:
- RED: Added adapter and metric regressions before implementation. The targeted run showed 10 failures and 129 passes; two integration failures initially exposed a test-fixture setup issue. After correcting that setup, both integration cases failed on the intended behavior: product-only queries remained present, and empty results returned unavailable.
- GREEN: The same three targeted test modules passed: 139 passed, 1 warning.
- Regression coverage includes empty/error/success seed mixtures, all-empty results, normalized product-only filtering, 에어컨 소음 against 소음, 에어컨추천 against 추천, stripped partial matching against 소음원인, axis metrics, cached recomputation without fetching/classification, and unchanged volume-mode results.

Verification:
- backend/.venv/bin/python -m pytest backend/tests -q
- Result: 1458 passed, 1 deselected, 2 warnings in 143.62 seconds.
- Warnings: Pydantic class-based configuration deprecation and joblib physical-core detection fallback.
- Scoped git diff --check passed.
- Tests use fake responses/MockTransport with network guards; no live network was used.

No commit created. Parallel jobs' changes outside the brief were left untouched.
