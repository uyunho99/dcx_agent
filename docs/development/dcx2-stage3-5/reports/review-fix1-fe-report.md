# Review fix 1 — frontend report

Implemented the frontend portion of R-111: C4, C7, G1, and G2. All edits made by this job are under `frontend/`, plus this report. No commits were created. The pre-existing decision-log/review-report changes and parallel backend work were left untouched.

## Changes

### C4 — training-eligible labels

- Added optional `Overview.trainable` to the frontend wire contract.
- `trainingLabels` now uses `overview.trainable ?? overview.accepted` for both the displayed count and empty-state decision. Explicit zero remains authoritative; absent overview remains unknown rather than empty.
- The training page displays this count as “학습할 라벨” and uses the same empty flag for fresh training and repository additional training.
- Regression coverage includes 40 human-only trainable labels with accepted=0, explicit trainable=0 with accepted>0, older responses without trainable, and the rendered training page's count and enabled actions.

### C7 — title and body evidence

- `QueueCard` renders the title as a separate heading above the body, preserving the existing text/body/content fallback order.
- Title-only documents display their title once. Documents without a title retain body/text fallback, and missing documents retain the missing-source message.
- The source focus target contains both title and body so the title is included in the source area when a card opens.
- Static-render regression tests verify separate title/body elements and their order, fallback fields, title-only documents, and missing documents.

### G1 — model-mode queue reasons

- Extended `QueueItem.reason` with `model_uncertain` and `model_disagree`.
- Added shared `queueReasonLabel` and `queueReasonSummary` helpers, used by the card and queue summary respectively.
- Model mode shows counts for “모델 불확실” and “모델 멤버 불일치”; LLM mode keeps its existing grade-mismatch/failure summary. Missing counts default to zero.
- Read the specified plan-worktree `02-design-r2.md`. It names the reason codes but does not prescribe Korean labels for them, so the controller brief's exact fallback labels were used.
- Vitest covers both model labels, existing LLM labels, audit/reissue fallbacks, mode-specific summaries, and missing counts.

### G2 — previous-visit counts

- Kept `useLabelSeen`'s existing once-per-screen/session/version behavior and read-only guard.
- Registered the overview-fetch effect before the seen hook, starting the first overview request before `/seen` without awaiting `/seen` completion.
- No client baseline or count reset was added. Overview continues to display the server's `changes` values directly.
- The screen lifecycle regression test leaves `/seen` pending, verifies that overview loads, checks that completing `/seen` leaves displayed counts intact, then verifies that polling displays updated server counts without another seen call. Existing hook coverage still checks read-only and replay behavior.

## Test-first evidence

Wrote the new regression tests before production edits. The targeted initial Vitest run failed on the human-only training helper/page, missing title, and overview/seen invocation order. The queue helper suite failed because the new helper did not yet exist. Implemented the fixes afterward.

## Verification

| Command | Result |
| --- | --- |
| `npm --prefix frontend test -- --run` | PASS: 40 files, 221 tests |
| `npm --prefix frontend run lint` | PASS: exit 0, no lint diagnostics |
| `cd frontend && npx next build --webpack` | PASS: compilation, TypeScript check, and static generation of 14 pages |
| `cd frontend && npx tsc --noEmit --incremental false` | PASS: exit 0, no type errors |
| `git diff --check -- frontend` | PASS |

Vitest/build emitted the environment's Node `DEP0205` (`module.register`) deprecation warning; it did not fail either command.

## Integration boundary

At inspection, `backend/app/label/overview.py` and `backend/app/routers/training_v2.py` did not yet expose `trainable`, and the overview/seen implementation still used `lastSeenAt`. As the brief explicitly permits, this frontend targets overview `trainable` with an accepted fallback. Correct human-only eligibility depends on the parallel backend job publishing `trainable`; correct previous-visit counts depend on its `prevSeenAt` implementation. Frontend request initiation order does not guarantee server processing order. No backend files were edited and no live backend/browser end-to-end claim is made.

Status: frontend fixes complete; frontend verification passed; backend contract integration remains with the parallel job; uncommitted.
