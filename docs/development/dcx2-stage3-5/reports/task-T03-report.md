# T03 report — 등급 규칙

Status: implemented; focused tests pass. Full-suite verification is blocked by collection errors in the parallel T02 task.

## Implementation

- Added `SEM`, `GRADE_FIELDS`, and `RULE_VERSION = "r1"` exactly as specified.
- Added `grade(tags)` with core = anchor and at least two semantic tags and situation; supporting = anchor and at least one semantic tag excluding core; otherwise non.
- Added `grade_probs(p)` using a six-Bernoulli dynamic program under field independence and the exact section 4.2 formulas.
- No `near_boundary` function or boundary escalation rule (D-143).
- Added the six exact supplied product-spec rows, worked example, probability normalization/range checks, and a deterministic 100,000-sample Monte Carlo check. Exhaustive testing also covers all 256 binary tag combinations and their degenerate probability distributions.

## Exact files created

1. `backend/app/label/__init__.py`
2. `backend/app/label/rule.py`
3. `backend/tests/label/test_rule.py`
4. `.superpowers/sdd/03-plan/task-T03-report.md` (this requested report)

No existing files modified. `backend/tests/work` has no `__init__.py`; matched that layout without creating a test package initializer. T02-owned files were not edited. No git write commands, commits, installations, or network operations were performed.

## TDD evidence

Tests were created before either implementation file.

### RED

Command (from repository root):

```sh
cd backend && .venv/bin/python -m pytest tests/label/test_rule.py -q
```

Output (exit 2):

```text
__________________ ERROR collecting tests/label/test_rule.py ___________________
tests/label/test_rule.py:7: in <module>
    from app.label.rule import GRADE_FIELDS, RULE_VERSION, SEM, grade, grade_probs
E   ModuleNotFoundError: No module named 'app.label'
ERROR tests/label/test_rule.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 warning, 1 error in 0.06s
```

Expected failure: the new label package and grading functions had not been implemented.

### GREEN

After adding the minimal implementation, ran the same command:

```sh
cd backend && .venv/bin/python -m pytest tests/label/test_rule.py -q
```

Output (exit 0):

```text
...........                                                              [100%]
11 passed, 1 warning in 0.09s
```

Both runs emitted the existing `app/config.py:12` Pydantic class-based config deprecation warning.

Refactor review: the implementation is already a small, single-source rule module with an explicit DP and no redundant abstraction; no further refactor was necessary.

## Full suite

Ran once as requested:

```sh
cd backend && .venv/bin/python -m pytest -q
```

Output (exit 2):

```text
_______________ ERROR collecting tests/vectors/test_embedder.py ________________
tests/vectors/test_embedder.py:9: in <module>
    from app.vectors.embedder import EmbedderUnconnected, FakeEmbedder, VoyageEmbedder, get_embedder
E   ModuleNotFoundError: No module named 'app.vectors'
________________ ERROR collecting tests/vectors/test_search.py _________________
tests/vectors/test_search.py:3: in <module>
    from app.vectors.search import cosine_topk
E   ModuleNotFoundError: No module named 'app.vectors'
_________________ ERROR collecting tests/vectors/test_store.py _________________
import file mismatch:
imported module 'test_store' has this __file__ attribute:
  /Users/persona1/Desktop/dcx_agent-dcx2-stage3-5/backend/tests/context/test_store.py
which is not the same as the test file we want to collect:
  /Users/persona1/Desktop/dcx_agent-dcx2-stage3-5/backend/tests/vectors/test_store.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
ERROR tests/vectors/test_embedder.py
ERROR tests/vectors/test_search.py
ERROR tests/vectors/test_store.py
!!!!!!!!!!!!!!!!!!! Interrupted: 3 errors during collection !!!!!!!!!!!!!!!!!!!!
1 warning, 3 errors in 1.83s
```

The full suite stopped during collection; no claim of a full-suite pass is made. These failures are in T02-owned files and were left untouched.

## Self-review and concerns

- Verified the constants, tag order, six supplied rows, and formulas against the brief and design section 4.2.
- Verified exact worked-example output: `{'core': 0.6698887, 'supporting': 0.27328839999999993, 'non': 0.056822900000000065}`.
- All binary combinations confirm anchor gating, semantic count thresholds, situation gating, and deterministic probability endpoints. Seeded random probability cases verify normalization and bounds.
- Inputs are assumed to contain complete binary tags or valid probabilities in `[0, 1]`, as required by the interfaces; no additional validation policy was introduced.
- `git diff --check` exited 0. The new files are untracked and remain for the controller to commit; this command does not validate untracked contents.
- Remaining concern: full-suite verification must be repeated after T02 resolves its collection errors. Shared-worktree status showed T02's untracked `backend/tests/vectors/`; those changes were preserved.
