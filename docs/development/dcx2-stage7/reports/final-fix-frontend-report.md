# Stage 7 final review fixes — frontend

Status: complete (frontend scope). Reviewed both final-review reports and D-259–D-266. No backend files, decision-log entries, git index, or commits were modified by this worker. Backend changes visible in the shared worktree belong to the parallel worker.

## Changes

- **Opus I3 / D-266:** typed `stage7.tag_calls` and `relevant_false`; progress uses `tag_calls` directly. The original progress reader already used the correct key, so this item required contract/fixture verification rather than reproducing a frontend defect. The complete report fixture distinguishes `tag_calls: 84` from `llm_calls: 91`.
- **Opus I4 / Codex 8:** labeling banner now reads `relevant_false`. Tests use the actual status envelope and report keys rather than the nonexistent `irrelevant` key.
- **Opus I5 / Codex 5:** required `quoteSource` in `EvidenceItemView`; highlights use its full text and Unicode code-point offsets. Location labels also use `quoteSource`. The body preview remains separate and unhighlighted. Title, body, comment, emoji, unverified, and beyond-preview offsets are covered.
- **Opus M5 / Codex 9:** novelty badges require `noveltyShown`; the novelty reason remains supporting text. Tests ensure even a high/very_high value cannot override a false flag.
- **Opus M6:** the stage-six action navigates to `/pipeline/evidence?start=1`. Evidence consumes the signal once after status and prerequisites load, removes it from the URL, and starts the version-scoped run. Read-only/conflicting views and running jobs do not start another run; stale evidence starts fresh.
- **Opus I2 / M10:** stale warnings require a previous run; stale selected details show “다시 실행 후 열람할 수 있습니다.” instead of a permanent skeleton. Old query/support content is suppressed.
- **Opus M11:** Artifact mention counts are displayed; Known Insight stable IDs are mapped to current one-based list positions for `Known Insight #2와 같은 내용`; partial results include explicit retry/skip guidance.
- API wrappers retain backend response envelopes without aliases or field rewriting. Shared frontend fixtures copy the router's camelCase item/status fields, raw snake_case context fields, and `assemble.stage_report` keys, extended by D-266. GET context and refresh-new responses are both checked.

## TDD and verification

Before implementation, targeted Vitest runs produced **12 failing display/labeling/navigation tests** and **2 failing controller tests**. These reproduced the requested frontend defects. I3 was already passing with the correct `tag_calls` reader and is explicitly treated as a regression check, not a fabricated failing test.

After implementation:

- Targeted suites: **5 files / 74 tests passed**.
- `npx tsc --noEmit --incremental false` in frontend: passed.
- `npm --prefix frontend test` (one final full run): **56 files / 539 tests passed**.
- `npm --prefix frontend run lint` (one final run): passed with no lint findings.
- `git diff --check -- frontend`: passed.
- Next build intentionally skipped. No browser/live-backend integration run was performed.

## Concerns / handoff

The backend contract work is concurrent. At final inspection, `assemble.stage_report` included `tag_calls`, but the router still did not contain `quoteSource` or `noveltyShown`. The backend worker must finish D-266 on both context/persona GET items and refresh-new items before combined runtime verification. Frontend cards intentionally require the new contract; they do not fall back to highlighting unrelated body text.

Known Insight numbering follows the current version's list order. If that list cannot be loaded or the matched ID has been removed, the card retains the generic match label rather than inventing a number. Backend counter additions outside the requested fields remain accepted through the report's open additional-key type.
