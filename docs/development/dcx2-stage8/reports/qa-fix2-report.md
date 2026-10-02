# Stage 8 browser QA fix round 2

Status: complete; Q2-1, Q2-2 and Q2-3 implemented and verified.

## Changes

- **Q2-1:** The evidence-package fixture now writes deterministic SHA-256 author hashes into segment documents, matching the synthetic source's two-documents-per-author assignment. The default session has 88 documents with non-null hashes and 44 distinct authors. A four-document concept basis now reports two authors. Failed-card API responses retain `card: null` and include `package_counts` from the Persona's package metrics and Context list; the header displays these counts (16 documents, eight authors, two Contexts for the QA failed Persona).
- **Q2-2:** Concept inputs resolve Persona-wide Desire references to selected Contexts containing the same document in the evidence index. Unresolvable references are excluded, preserving reference numbering and preventing generated or edited pain points with null Context IDs. Source lines reuse `contextLabels.channels`, display 본문 / 제목 / 댓글 n (one-based), and retain the Context ID without raw offsets or object-field labels.
- **Q2-3:** `make_persona_qa.py --second-session` creates another confirmed same-product session using `seed + 1`, without stage-eight results, and prints `second_sid` in its JSON output. The original session retains its deliberate failed Persona. Both sessions have `bk=LG 에어컨`.
- Highlighting code was untouched; the conditional CCM emoji regression addition was therefore not needed.

## TDD and validation

- Before implementation: four new pytest regressions failed (missing segment hashes, missing failed-card counts, null pain-point Context, unsupported CLI flag); two new Vitest regressions failed (null-card header and hydrated source formatting). Existing tests in the two frontend files passed.
- After implementation: targeted backend validation passed **59 tests**; targeted frontend validation passed **47 tests**. Existing basis expectations were updated from zero authors to the fixture's actual distinct-author counts.
- Full backend suite (`cd backend && .venv/bin/python -m pytest`): **2,020 passed, 2 deselected, 2 warnings in 314.67 seconds**, exit 0; executed once. The repository default excludes the two opt-in performance tests. Warnings were the existing Pydantic class-config deprecation and joblib physical-core detection fallback.
- `npm --prefix frontend test`: **593 passed across 59 files**, exit 0; executed once for final full validation.
- `npm --prefix frontend run lint`: **passed**, exit 0; executed once.
- `git diff --check`: passed.
- `next build` skipped as requested.

## Controller follow-up and limits

- The QA backend on port 8321 was neither stopped nor restarted and was confirmed still listening. Reload the changed Python implementation before browser rechecking if the running server does not autoreload.
- Existing data is not migrated. Use an unused seed pair or a fresh data directory to generate sessions with populated hashes, and regenerate existing concepts to replace stored null Context IDs and old basis text. Example:

  ```sh
  backend/.venv/bin/python backend/tests/scripts/make_persona_qa.py LOCAL_DATA_DIR --seed 100 --second-session
  ```

- The script refuses to overwrite existing deterministic sessions; choose seeds for which both the primary session and the seed-plus-one session are unused. Add `--big-persona` for the primary ten-Context case.
- The second session intentionally has no stage-eight output; confirm insights in the first session before checking the second session's 이전 세션 추천 drawer.
- Browser QA was not rerun here; validation used backend tests and rendered frontend response-shape tests.
- No git add, commit, subagents, or edits to the running QA dataset.
