# T9 report — complete

Implemented only the T9 backend files:
- `backend/app/evidence/tabs.py`
- `backend/app/evidence/novelty.py`
- `backend/app/evidence/prompts/novelty.v1.md`
- `backend/tests/evidence/test_tabs.py`

## Behavior

All-tab selection preserves Known Insight badges without a quality penalty. New-tab selection excludes handed rag/doc IDs, current semantic matches, and cosine duplicates at the inclusive 0.95 boundary, then reapplies the existing 4.4 selection. The boundary comparison allows one floating-point ULP for normalization rounding. Candidate IDs and exclusion counts are deduplicated. The exclusion message is exactly `N건이 Known Insight와 같아 빠졌습니다 → 전체 탭에서 보기`. Defaults are Context=new, desire support=all, counter=all.

New-tab expansion requests 50 candidates per round, up to three rounds, and stops when ten are selected or the source is exhausted. Injected preparation handles tagging and Known Insight judgment. Coverage supplementation requests 15 candidates once per tab computation; those candidates pass through the same preparation/exclusion path and remain available through later expansion rounds. The returned Selection preserves coverage, missing dimensions, rare fallback and dpp_fill. NewTab records rounds, exclusions, retained candidate/tag data and parameter values.

Refresh accepts cached search callbacks and has no tagging or novelty invocation. Current Known Insight snapshots filter stable IDs, including removal during an expansion callback. The deletion test drops the actual TagCache pair, deletes the current item and verifies immediate restoration and badge removal without error. Handed-document vector comparison uses original document vectors, not statement vectors from the combined known_vectors result.

Novelty uses one evidence.novelty registry task with a Pydantic schema, final new-tab documents, up to five nearest-centroid Core representatives and the Known Insight list. Empty tabs make no call; failed responses remain unjudged without a module-level retry. Provider/schema retries remain owned by the existing registry. Only requested document IDs are accepted, reasons must be one line, and only high/very_high set show_novelty. All-only documents have null novelty and reason.

## TDD and validation

1. Wrote test_tabs.py first and ran it: RED, missing app.evidence.tabs import.
2. Implemented modules/prompt: initial implementation exposed the exact-0.95 normalization boundary failure; fixed it.
3. Targeted run: 19 passed, one existing Pydantic configuration warning.
4. Refactored handed-input extraction after GREEN.
5. Ran the requested full command exactly once after the refactor:
   `backend/.venv/bin/python -m pytest backend/tests/evidence -q`
   Result: **154 passed, 2 warnings, 8.04s**.
6. `git diff --check` passed. No staging or commits. No frontend files edited.

Additional tests cover coverage supplement exclusions/preparation, cache-only refresh expansion, current origin/type filtering, default tabs, five nearest Core representatives, one novelty task/input payload, foreign response IDs, failed/empty novelty responses and schema-invalid levels/reasons.

## Integration notes / concerns

No T9 blocker. Existing warnings concern Pydantic class Config deprecation and joblib physical-core detection.

T10/T11 own persistence and orchestration: call novelty once after final selection; enrich new/core rows with prepared text or quotes; provide Context-scoped core rows and centroid; save only the requested Context's new tab during refresh. Use apply_novelty with retained judgments during refresh, leaving newly selected unjudged documents null. No new novelty calls belong in refresh.

Expansion callbacks own the Context allow set, relevance cursor and retrieval through evidence.search.filtered_topk. prepare(rows) must tag and judge, return stable-ID tags, and make vectors/docs available. Cache-only refresh callbacks require preloaded cached tags/vectors/docs. Pass a current-list callback for known_items when mutations can occur during injected work; a fixed list intentionally represents a fixed snapshot. Sentence-KI addition/pair judgment and TagCache.drop_known invocation belong to the caller. Version/run validation and context-scoped writes remain T11/T12 responsibilities.

Concurrent frontend and decision-log changes present in the worktree were left untouched.
