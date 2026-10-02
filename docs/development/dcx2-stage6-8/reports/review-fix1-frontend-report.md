# Frontend review fix 1

Status: complete on `feature/dcx2-stage6-8`.

The final SegmentScreen registers unsaved edits with DirtyProvider, keeps the registration during the debounce and in-flight save, and clears it after the latest successful save or screen cleanup. Pending edits are retained in a ref and flushed on unmount, so navigation within the 600 ms debounce sends the latest draft instead of discarding it. Revisions prevent an older save from clearing the dirty state of newer edits.

At task entry, both allowed frontend files already contained uncommitted dirty-registration, unmount-flush, and regression-test changes. These were preserved. This task added two tests and changed the save queue to dispatch PATCH synchronously when idle, while retaining ordered writes behind an in-flight save. Settled writes release the queue, allowing subsequent idle flushes to dispatch immediately.

Tests added before the implementation change:

- Pending edits followed by unmount dispatch PATCH during cleanup with the latest edits, including multiple edits before a rerender; the old debounce does not send a duplicate.
- Dirty registration remains true through the 600 ms debounce and unresolved PATCH, then becomes false after successful completion.

RED: `npm --prefix frontend test -- clustering` exited 1: 43 passed, 1 failed. The new immediate-unmount test observed zero PATCH calls during cleanup. The dirty-lifecycle test already passed against the pre-existing changes; this run does not claim to reproduce the original committed implementation's missing dirty registration.

GREEN: after the queue change, `npm --prefix frontend test -- clustering` exited 0: 44 tests passed. Existing cases also verify unmount flushing, failed-save dirty retention, and an older save completing while newer edits remain pending.

Validation:

- `npm --prefix frontend run lint`: passed, exit 0.
- `npm --prefix frontend test`: run once; passed, exit 0; 52 test files and 434 tests.
- Scoped `git diff --check`: passed.

Concerns: actual browser shutdown can interrupt ordinary fetch requests despite immediate dispatch; this change guarantees dispatch on idle unmount, not server persistence after closing the browser. When an older save is in flight, the latest draft stays queued behind it to preserve write ordering. Tests use the existing mocked-hook harness rather than a browser navigation integration test. Vitest emitted the existing Node DEP0205 module.register deprecation warning, without affecting results.

Only SegmentScreen.tsx, clustering/page.test.ts, and this requested report were edited by this task. Pre-existing backend and compare-screen changes were left untouched. No staging, commits, subagents, or reviewers were used.
