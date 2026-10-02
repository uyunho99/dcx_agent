# Stage 7 browser QA fix round 2

Date: 2026-10-02. Worktree: `feature/dcx2-stage7`.

## Changes

- **E-F1:** novelty labels now display `very_high → 매우 높음`, `high → 높음`, `medium → 보통`, `low → 낮음`, and `none → 없음`. The badge remains gated by `noveltyShown`.
- **E-F2:** adding a card to Known Insight now awaits the doc save, immediately invokes `refresh-new` for the Context selected when the action began, then reloads server status and evidence. Changing the selection while the save is pending cannot redirect the refresh. Removed the blanket optimistic `knownChanged=true` assignment to all completed rows. Other completed Contexts retain the server's change marker; refreshed rows use the server's cleared marker.
- **E-F3:** Context, Persona, and refresh response items expose `known: {handed: boolean, kiId: string | null}`. Handed rag documents are recognized independently of semantic `knownMatch`, including when that value is `none`. Cards show `Known Insight와 같은 내용`, with ` #n` appended when the stable KI ID resolves to a display number. Already handed cards retain their added state after reloading.
- **E-F4:** lowercase API dimension keys render as `Sense`, `Feel`, `Think`, `Act`, `Relate`, and `Outcome`; only supplied tags appear.

## Change-marker investigation

The old UI deliberately omitted automatic refresh and optimistically marked every completed Context changed. That behavior has been replaced with the save → originating Context refresh → authoritative status sequence.

The specific reported **3 → 4** increase was not reproduced in the backend. Read-only inspection of the existing QA database found refreshed rows with `knownChanged=false` and updated Known Insight snapshots. An isolated test using the actual `make_segment_qa.py --confirm-all` corpus, default fake LLM, HTTP routes, and worker pipeline refreshed every Context after adding one document: the marker count decreased by exactly one per refresh, each refreshed row was clear, and the cumulative LLM call count stayed unchanged. The API regression also checks repeated refresh, semantic KI matches, and isolation from other rows. No speculative changes were made to backend snapshot invalidation.

## TDD and verification

Tests use lowercase API tags, real item contracts, real document-add responses, stable KI IDs, and actual pipeline output.

- Red: UI regressions failed in 10 cases before implementation (43 existing cases passed); API regression failed on the missing `known` field. The QA-corpus marker/zero-call regression already passed before the UI fix, narrowing the marker investigation.
- Targeted green: **24 API tests passed**; **57 UI tests passed**, including selection changes during save, immediate automatic refresh, manual refresh marker clearing, polling stability, handed/semantic badges, and localized labels.
- `backend/.venv/bin/python -m pytest backend/tests -q -o addopts=''`, once, including opt-in performance tests: **2,003 passed**, exit 0, **588.28 seconds**. Two existing warnings: Pydantic class-based configuration deprecation and joblib physical-core detection fallback.
- `npm --prefix frontend test`, once: **560 passed, 56 files**, exit 0.
- `npm --prefix frontend run lint`, once: **passed**, exit 0.
- `git diff --check`: passed.

Logs for this run: `/private/tmp/stage7-qa2-red-ui.log`, `/private/tmp/stage7-qa2-red-api.log`, `/private/tmp/stage7-qa2-red-backend.log`, `/private/tmp/stage7-qa2-green-api.log`, `/private/tmp/stage7-qa2-green-ui.log`, `/private/tmp/stage7-qa2-full-backend.log`, `/private/tmp/stage7-qa2-full-frontend.log`, and `/private/tmp/stage7-qa2-lint.log`.

## Scope and concerns

The existing statement-KI judgment behavior is preserved; the tested card/document-add recalculation uses cached judgments and makes zero LLM calls. The exact original browser 3 → 4 sequence remains unconfirmed; regression coverage now guards the corresponding UI and backend state transitions.

The QA backend listener on `:8320` remained running with PID 30417. No QA session was mutated by this task; integration tests use isolated temporary data. No browser replay or `next build` was performed. No git staging or commits were performed.
