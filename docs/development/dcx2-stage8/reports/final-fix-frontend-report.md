# Stage 8 final review fixes — frontend

Status: complete. Reviewed `final-review1.md`, `codex-branch-review1.md`, and controller rulings D-312 through D-316.

## Changes

1. **C1 / Codex #4:** stale Persona generation sends `{fresh: true}`; ordinary generation retains `{}`.
2. **I1:** API errors retain their structured `kind` and HTTP status through `ApiError`. Entry loads recognize `evidence_required` from status/cards and `not_ready` from cards when the persona status is none/idle. The exact empty-state copy and evidence navigation appear without first starting generation. A running worker's unpublished cards do not incorrectly show the empty state.
3. **I2 / Codex Minor 1:** InsightScreen uses the durable worker status, tracks the returned run ID, resumes polling on entry to an active run, and stops waiting on terminal worker state. Failed/interrupted derive runs show the required failure copy and reason, with retry/resume actions. Concept retries preserve the server mode/target. An untouched empty session shows introductory guidance. Publishing an intermediate revision does not prematurely end polling.
4. **Codex #6:** every `getInsights` reload also reads `/session/{sid}?version=...` for authoritative confirmations. Only IDs present in the loaded insight list reach local selection. Mount, polling, chat, and revert synchronize that selection; confirm still adopts the server mutation response. Filtering is presentation-only, so a server-retained ID can reappear when its insight returns.
5. **I3 / D-312:** explicit Context keyword and Persona artifact types; CCM reads Context keywords and Persona-level artifacts, including formatted mention counts.
6. **D-313:** typed `outdated` concepts suppress 8-F and show the exact regeneration copy and button. The outdated concept option is disabled in the chat target selector.
7. **D-314:** all three stale mutation paths use the exact actionable Korean copy; chat preserves this message instead of replacing it with generic edit failure.
8. **D-315:** `personaView.zoneName` owns complete A–F labels across the map, accessible summaries, tooltips, tables, CCM and detail view. Shared display helpers localize object keys, journey/sensitivity fields, evidence locations and radar labels. Metrics use two decimals, percentiles use integers, and counts use ko-KR grouping. Tree, bars and journey counts use the same formatting helpers.

Changes were limited to frontend source/tests and this report. No backend files were edited by this worker, no git add/commit was run, no subagents were used, and D-316 version UI/prompt-size deferrals remain untouched. Concurrent backend and controller changes in the worktree were left intact.

## TDD evidence

Before implementation, ran:

`cd frontend && npx vitest run src/components/persona/PersonaScreen.test.ts src/components/persona/finalReview.test.ts`

Result: **14 failed, 12 passed**, across two failing files. All 14 newly introduced cases failed before their fixes and passed afterward:

| Finding | Initial failing regression | Failure observed before implementation |
| --- | --- | --- |
| C1 | `C1 regenerates stale results with fresh true` | Request body was `{}`. |
| I1 | `I1 uses real cards fetch error kind ... on entry` × 2 | Both evidence_required and not_ready omitted the required empty state. Real API client/fetch path used. |
| I2 | `I2 resumes active run and stops on ...` × 2 | Entry failed to show processing for active runs. Cases continue through failed/interrupted, reason, enabled controls and recovery action. |
| I2 initial state | `I2 initial empty state is guidance, not failure` | Failure copy appeared before any run. |
| Codex #6 | `Codex6 reload and edit/revert synchronize server confirmed IDs` | No authoritative confirmation update after edit. |
| I3 | `I3 renders context keywords and persona artifacts in CCM` | Persona artifact row was empty. |
| D-313 | `D313 hides outdated concept and offers regeneration` | Required regeneration copy/button absent. |
| D-314 | `D314 ... stale uses actionable copy` × 3 | Chat/revert/confirm returned generic failure messages. |
| D-315 | `D315 localizes attribute keys and formats counts and metrics` | Counts lacked grouping and attributes used raw field keys. |
| D-315 | `D315 uses one zone label and formatted metric text in map/table/radar` | zoneName returned the name without its zone letter. |

The initial red output was captured in `/tmp/frontend-red.log`; the first green output in `/tmp/frontend-green1.log`. The same 26 cases then passed. Existing expectations for superseded zone/radar labels and the extra authoritative session fetch were updated to the new contracts.

Added five supplementary cases for status-endpoint evidence errors, running-card not_ready behavior, new-run polling across an intermediate revision, concept resume target, and confirmation filtering/restoration. Final focused run: **31 passed**. Real fetch is stubbed at the transport boundary; Persona status-error and cards-error tests execute the actual API clients rather than injecting the UI missing flag. Worker tests use fake timers and execute the screen's effects and event handlers.

## Verification

- Persona suite before the supplementary cases: **6 files / 95 tests passed**.
- `npx tsc --noEmit`: passed during implementation.
- Final `npm --prefix frontend test`: **58 files / 567 tests passed**, exit 0. Run once at the end.
- Final `npm --prefix frontend run lint`: passed, exit 0. Run once at the end.
- `git diff --check -- frontend`: passed before final verification.
- Next build deliberately skipped as requested.

## Decisions and remaining concerns

- No new evidence-presence endpoint or flag was assumed. `not_ready` is interpreted as the empty state only for none/idle sessions; `evidence_required` is authoritative. This avoids hiding active generation behind the entry empty state.
- Confirmations are absent from the specified D-312 insight wire envelope, so the API client enriches its result using the existing version-aware session endpoint. Each reload/poll therefore makes an additional session read. The two reads are not an atomic backend snapshot.
- Worker and concept contracts are typed explicitly. Card fields remain optional at the body level to tolerate existing historical/partial cards; Context keyword and artifact element shapes are explicit.
- The node tests validate real client requests and screen behavior but are not a live-browser or live-backend integration run. The backend worker's final D-312–D-314 implementation still needs combined integration verification.
- Vitest emitted the existing Node `module.register()` deprecation warning; tests and lint exited successfully.
