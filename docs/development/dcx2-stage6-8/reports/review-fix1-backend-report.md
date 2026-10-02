# DCX 2.0 stage 6 bundle 1 — backend review fixes

Worktree: `/Users/persona1/Desktop/dcx_agent-stage6-8`  
Branch: `feature/dcx2-stage6-8`

The worktree already contained fixes and regression tests for all three findings when this task began. Those changes were preserved and inspected. RED was independently verified against the three original production modules from `HEAD` in an isolated temporary copy, leaving the shared worktree intact. This pass additionally fixed an unavailable-probability fallback uncovered by a new failing test and strengthened report-only comparison coverage. No staging, commits, subagents, or reviewers were used. No frontend files were edited during this pass; the existing comparison renderer was retained and checked. The other worker's SegmentScreen changes were left untouched.

## Finding 1 — nullable model output

- **Files:** `backend/app/segment/dims.py:162`, `:236`, `:307`.
- Nullable probability and semantic mappings are guarded before nested access. Explicit `tagProbs: null` remains distinguishable from a legacy missing mapping, so original `sem.act` labels cannot substitute for an unavailable model head. Missing Act probabilities increment `act_unknown`, not `act_mismatch`, in both context and overall summaries.
- Searched all `tagProbs` and `pred_entropy` references under `backend/app/segment/`. `backend/app/segment/signals.py:12` already carries nullable entropy through unchanged; `backend/app/segment/store.py:24` accepts SQL NULL. No additional entropy guard was needed.
- **Tests:** `backend/tests/segment/test_dims.py:216` covers Core exports with null probabilities/entropy, nested null semantic mappings, original `sem.act`, and cached resume. `backend/tests/segment/test_pipeline.py:365` exercises the synthetic pipeline through pause, resume, and another resume, verifying null entropy survives on Core rows.
- **RED:** both original nullable-export regressions failed against `HEAD` with `AttributeError`. The newly parameterized `sem={'act': 0}` case also failed against the initially supplied fix: `act_unknown` was 1 instead of 2 (1 failed, 1 passed). The implementation was changed only after observing this failure.
- **GREEN:** both nullable dimension cases and the pipeline resume case passed in the focused regression run.
- **Full suite:** **1697 passed, 2 deselected, 2 warnings**, 289.72 s; no failures.
- **Concerns:** none known for valid stage-five null output. Non-null legacy semantic fallback remains supported.

## Finding 2 — generation and rows share a SQLite snapshot

- **Files:** `backend/app/routers/segment.py:83`, `:93`, `:216`, `:224`, `:244`, `:308`.
- `ConfirmationStore.snapshot()` starts one read transaction and reads the generation on that connection. Clusters, personas, contexts, docs, layer gates, document/author aggregates, and pagination totals reuse it. The request-local connection is cleared and closed when the snapshot exits.
- **Tests:** `backend/tests/segment/test_api.py:392` resets generation and rows from a second connection between generation and row reads for all four endpoints. `backend/tests/segment/test_api.py:421` resets after Persona rows are read, reproducing the reported old-rows/new-generation failure.
- **RED:** the original implementation failed clusters, contexts, docs, and Persona-after-rows interleavings (4 failed, 1 passed). Persona's generation-first interleaving alone passes the original ordering, which is why the complementary after-rows regression is required.
- **GREEN:** all five interleaving cases passed in the focused regression run.
- **Full suite:** **1697 passed, 2 deselected, 2 warnings**, 289.72 s; no failures.
- **Concerns:** the snapshot covers SQLite data. Session JSON and report JSON are separate files and do not participate in that transaction.

## Finding 3 — stage-six version comparison

- **Files:** `backend/app/context/versions.py:300`; existing renderer at `frontend/src/app/pipeline/compare/page.tsx:68`.
- Stage six reads `segment/stage_6.json`, matching the pipeline writer at `backend/app/segment/pipeline.py:390`, and reads saved confirmations from the version-local `segment.sqlite` using a read-only connection and one read transaction. Summary fields include saved names, desire, goals, action, and confirmed/total counts. Missing/reset results stay empty without creating a segment database. Stages 0–5 retain their existing branches.
- A canonical full-report hash detects changes outside the compact displayed report; per-document coverage, code tables, and context detail are omitted from the displayed report summary. The existing frontend renderer shows version columns, report absence, saved fields, and confirmation counts.
- **Tests:** `backend/tests/context/test_versions_stage6.py:145` covers copied equality, report-only changes outside the displayed summary, saved persona/context fields, report metrics, completed-versus-reset comparison, and absence of filesystem creation for reset results. Existing `frontend/src/app/pipeline/compare/page.test.ts:12` checks rendering of saved fields and report absence.
- **RED:** the original implementation incorrectly returned `same: true` after saved confirmation changes. The strengthened report-only assertion independently failed against `HEAD` as well.
- **GREEN:** the comparison regression, including strengthened report-only coverage, passed in the required segment/context suite; the existing frontend rendering test also passed.
- **Full suite:** **1697 passed, 2 deselected, 2 warnings**, 289.72 s; no failures.
- **Concerns:** detailed per-document report changes are detected via the hash but not expanded in the UI. JSON reports and SQLite confirmations have separate storage transactions.

## Verification

- Isolated original-code regression run: **7 failed, 1 passed**, establishing failures for all three findings.
- Focused fixed-code regression run: **9 passed** (including the additional nullable semantic-label case).
- `backend/.venv/bin/python -m pytest backend/tests/segment backend/tests/context -q`: **404 passed, 1 deselected, 2 warnings**, 143.00 s.
- `backend/.venv/bin/python -m pytest backend/tests -q` (run once): **1697 passed, 2 deselected, 2 warnings**, 289.72 s. Deselections follow the repository default exclusion of performance tests.
- `npm --prefix frontend test -- src/app/pipeline/compare/page.test.ts`: **1 passed**. Node emitted its existing `module.register()` deprecation warning.
- `git diff --check`: **passed** after the final suite.

Existing runtime warnings concern Pydantic class-based configuration deprecation and joblib physical-core detection fallback. No unrelated warning cleanup was attempted.
