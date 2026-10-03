# R1–R3 fix report

Date: 2026-10-03. Branch: `feature/label-gpt-only`; starting HEAD: `86ead3a`.

## Changes

- R1: GPT-only candidates now come from all completed GPT votes without a final row, using a single SQL anti-join. A GPT cursor advanced by a cross sync with an empty Jev cache can no longer hide completed votes. Existing final rows are preserved; only missing projections are materialized in Python. The join uses the final table's document primary key, avoiding per-document queries for the roughly 90k-row workload.
- R2: Rule/question version invalidation checks only checkpoints belonging to caches active in the current mode. An inactive Jev checkpoint cannot repeatedly invalidate GPT-only results. Jev checkpoints remain available for cross mode, where version changes and GPT-only projections are reconsidered.
- R3: The GPT-only notice and worker filtering require LLM mode. Overview passes its local radio selection before Start and its saved overview mode after Start.

## RED — before implementation changes

`backend/.venv/bin/python -m pytest backend/tests/label/test_gpt_only_final.py -q -p no:cacheprovider`

```text
FAILED test_gpt_only_recovers_vote_consumed_by_cross_sync
FAILED test_gpt_only_ignores_inactive_checkpoint_version[rule]
FAILED test_gpt_only_ignores_inactive_checkpoint_version[questions]
3 failed, 13 passed, 1 warning in 0.57s
```

R1 observed `[]` instead of one `gpt_only` row. Both R2 cases created a GPT-only row after the version change, then lost it on the second sync. The tests additionally require a subsequent rebuild to return zero, preventing repeated deletion/recreation from masking R2, and verify return to cross mode.

`npm --prefix frontend test -- src/components/label/labelerMode.test.ts`

```text
Test Files  1 failed (1)
     Tests  2 failed | 3 passed (5)
```

Both new tests expected `showNotice: false` for model mode but received `true`: once through the overview mode and once through the local selection override. They also cover LLM notices and worker filtering.

## GREEN — final verification

| Command | Final result |
| --- | --- |
| `backend/.venv/bin/python -m pytest backend/tests/label -q -p no:cacheprovider` | `244 passed, 1 warning in 12.63s` |
| `backend/.venv/bin/python -m pytest backend/tests -q -n auto -p no:cacheprovider` | `2690 passed, 20 warnings in 114.47s (0:01:54)` |
| `npm --prefix frontend test` | `Test Files 71 passed (71)`; `Tests 778 passed (778)` |
| `npm --prefix frontend run lint` | Exit 0, no diagnostics |

All four commands exited 0. Backend warnings concern Pydantic's class-based config deprecation and joblib's physical-core detection fallback; frontend tests emitted a Node `module.register()` deprecation warning. `git diff --check` also passed. No 90k-row benchmark was run.

## Files changed by this task

- `backend/app/label/route.py`
- `backend/tests/label/test_gpt_only_final.py`
- `frontend/src/components/label/labelerMode.ts`
- `frontend/src/components/label/labelerMode.test.ts`
- `frontend/src/components/label/Overview.tsx` — only the `labelerView` call.
- `docs/development/label-gpt-only/reports/fix-R1-R3.md`

No commit and no Next build. The port 3320 dev server was left alone. Pre-existing changes to `T4.md`, `build.json`, and `review.md` were untouched.
