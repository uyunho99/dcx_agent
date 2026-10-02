# Final fix report

Status: COMPLETE. Both final whole-branch review findings are fixed.

## Changes

- `frontend/src/lib/logic/startForm.ts:42`: normalize `analysisGoal` to null whenever its choice is the empty string, including a nonempty note. Valid saved choices remain preserved.
- `backend/app/context/models.py:208`: apply the same normalization in the before-validator. The unchanged after-validator at line 217 still requires an analysis goal when taskMode is missing or None.
- `frontend/src/lib/logic/startForm.test.ts:53`: regression for an old draft with `{choice: "", note: "메모"}`; asserts null normalization and valid start-form validation.
- `backend/tests/context/test_models_task_mode.py:77`: explore plus the note-only goal becomes None. Line 82 adds missing/None taskMode rejection cases. The existing empty-goal legacy rejection test at line 70 is unchanged.
- `frontend/src/app/pipeline/start/page.tsx:225`: banner type name comes from `labels.taskMode[form.taskMode || "explore"]` (`contextLabels` is imported as `labels`). This follows the current selection or restored metric draft; the remaining design §5.4 sentence is unchanged.

## RED — tests added before implementation

`npm --prefix frontend test -- src/lib/logic/startForm.test.ts`

```text
FAIL normalizes a legacy goal with a note but no choice
AssertionError: expected { choice: '', note: '메모' } to be null
Test Files  1 failed (1)
Tests       1 failed | 35 passed (36)
```

`backend/.venv/bin/python -m pytest backend/tests/context/test_models_task_mode.py -q -p no:cacheprovider`

```text
FAILED test_goal_with_note_but_no_choice_is_none
ValidationError: analysisGoal.choice
Input should be 'needs', 'marketing', 'concept' or 'segment'
[type=enum, input_value='', input_type=str]
1 failed, 13 passed, 1 warning in 0.05s
```

Both expected failures were observed before changing implementation. The two new legacy rejection cases already passed, as intended. RED output was redirected to `/tmp/dcx-final-red-frontend.log` and `/tmp/dcx-final-red-backend.log` and displayed with `cat`; that shell wrapper returned the status of `cat`, while the test output above records the failed test runs.

## GREEN — requested verification

All four commands completed with exit 0 after the fixes.

`backend/.venv/bin/python -m pytest backend/tests/context -q -p no:cacheprovider`

```text
210 passed, 2 warnings in 7.37s
```

`npm --prefix frontend test`

```text
Test Files  50 passed (50)
Tests       356 passed (356)
Duration    2.11s
```

This includes all 36 start-form tests and the new backend regression and legacy cases.

`npm --prefix frontend run lint`

```text
> frontend@0.1.0 lint
> eslint
```

No lint diagnostics.

`npm --prefix frontend run build -- --webpack`

```text
▲ Next.js 16.1.6 (webpack)
✓ Compiled successfully in 1352.1ms
  Running TypeScript ...
  Collecting page data using 9 workers ...
✓ Generating static pages using 9 workers (14/14) in 138.4ms
  Finalizing page optimization ...
  Collecting build traces ...
○ (Static) prerendered as static content
```

`git diff --check` passed. Source diff review confirmed only the five authorized source/test files changed, plus this requested report. No git add/commit or agents were used.

## Concerns

- No blocking concerns.
- Non-blocking warnings: Pydantic class-based Config deprecation; joblib could not detect physical cores and fell back to logical cores; Node DEP0205 module.register deprecation during frontend tests/build.
- Browser interaction QA was not run. The banner was verified by source inspection and the production TypeScript/build checks.
- Pre-existing untracked `docs/development/dcx2-stage0-task-mode/build.json` was left untouched.
