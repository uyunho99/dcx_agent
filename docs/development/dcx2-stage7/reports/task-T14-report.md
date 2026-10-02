# T14 report

Status: complete (frontend implementation and offline verification).

## Scope

Reviewed and continued the existing uncommitted T14 work against task-T14-brief.md, design sections 4.9, 9/9.1, 10 and 14, stage-7 sections 6–7, and mockup s4. Kept the correct existing implementation; no backend files, unrelated decision-log changes, git staging, or commits were made.

- Added `/pipeline/evidence` with legacy-session fallback, selected-version reads, read-only write protection, polling and completion refresh.
- Evidence screen groups Personas by cluster, shows Context status badges, Coverage and discovery counts, permits completed-row browsing during execution, and locks pending rows and persona navigation until completion.
- New discoveries are the default tab. Both tabs, exact empty-state/prerequisite/stale/failure copy, eight-query disclosure and fallback copy, counter/rare disclosure, and Persona support disclosure are covered.
- Evidence cards display verified quote highlighting, channel/location, dimension tags, band, novelty, known-match badge and Known Insight addition. Unicode offsets use `Array.from(text)` with an emoji regression test.
- Known Insight addition uses the existing typed document-add API (`type: 'doc', doc_id`, matching SourceCard). Completed rows retain the required recalculation notice until explicit refresh; refresh and skip carry the evidence generation and selected version.
- Corrected inherited automatic refresh of the selected row so it retains the D-223 recalculation action alongside other completed rows.
- Corrected stale row mutation guards, immediate clearing of prior-selection evidence, failed-run recovery when no failed rows exist, and Persona support reloading as Contexts finish during the same run.
- Progress bar uses completed/skipped Context counts and the Context total, matching its displayed count without assuming a scale for API `progress`.
- Sidebar step 7 links to evidence for sessions with `prep.derivedRef`; legacy sessions retain the disabled step. `completion.evidenceDone` advances `completedThrough` to 7. The persona button only navigates to `/pipeline/personas` (D-255).

## TDD and validation

Added regressions first and observed four failures for Known Insight refresh behavior, selection clearing, stale actions and failed-run recovery. Implemented fixes and observed green. Added two further failing regressions for in-run Persona support refresh and progress scale independence; implemented fixes and observed green.

Final checks (full npm test and lint each executed once at the end):

- `npm --prefix frontend test`: PASS — 56 files, 522 tests; evidence subset 49 tests.
- `npm --prefix frontend run lint`: PASS — no errors or warnings.
- `frontend/node_modules/.bin/tsc --noEmit --incremental false` from frontend: PASS.
- `git diff --check`: PASS.
- Next build skipped as requested.

## Concerns / verification limits

No live backend or browser integration was run. API behavior is checked offline with mocked transports; the evidence router was not present in this worktree during review, so end-to-end compatibility still depends on the parallel backend work. The 1024px layout requirement is verified through shrinkable grid/min-width/wrapping class assertions as requested, not browser geometry. Vitest emitted only Node's existing module.register deprecation notice.

Report: `.superpowers/sdd/03-plan/task-T14-report.md`.
