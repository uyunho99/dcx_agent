# T1 implementation report

Status: Implementation complete; dependency installation verification blocked by sandbox DNS/network access. Full backend suite passes in the existing worktree environment.

## Changes

- `.github/workflows/ci.yml`: main pull-request/push triggers, read-only contents permission, per-ref concurrency with PR-only cancellation; Ubuntu backend Python 3.12 with pip caching and constraints; Ubuntu frontend Node 26 with npm caching and install/lint/test/build steps.
- `backend/app/main.py`: only the `/health` function changed; returns `DCX_RELEASE_SHA` or `dev` alongside status.
- `backend/requirements-dev.txt`: added `pyyaml`.
- `backend/constraints.txt`: 141 exact version pins from the developer venv.
- `backend/tests/test_health.py`: updated expected response and isolates the release environment variable.
- `backend/tests/ops/__init__.py`: empty package initializer.
- `backend/tests/ops/test_ci_workflow.py`: workflow contract assertions, including constrained install.
- `backend/tests/ops/test_health_release.py`: explicit release and default release HTTP tests.
- This report.

No T2 files modified; no git staging, commits, pushes, GitHub changes, or delegated agents.

## RED

Command:

```sh
backend/.venv/bin/python -m pytest backend/tests/ops/test_ci_workflow.py backend/tests/ops/test_health_release.py backend/tests/test_health.py -q -p no:cacheprovider
```

Before implementation: **3 failed, 1 passed, 5 errors** (2.40s). Five workflow fixture errors were caused by the absent workflow; three response assertions failed because release was absent. Tests were written and executed before implementation.

## GREEN

Same focused command after implementation: **9 passed**, 1 existing Pydantic deprecation warning (2.57s).

Full suite command:

```sh
backend/.venv/bin/python -m pytest backend/tests -q -p no:cacheprovider
```

Full suite result: **1514 passed, 1 deselected, 2 warnings in 144.10s**; exit 0. Warnings concern existing Pydantic configuration and joblib physical-core detection. `git diff --check` also passed.

## Constraints generation and installation

Source command (read-only developer environment):

```sh
/Users/persona1/Desktop/dcx_agent/backend/.venv/bin/python -m pip freeze
```

Captured stdout using subprocess and retained only `name==version` entries, excluding editable/direct URL/local entries. Applied the Darwin marker rule for names beginning with `pyobjc`. All 141 entries were ordinary pins, no exclusions or Darwin markers were needed; no other clearly macOS-only package was identified. A subsequent equality check confirmed the constraints file exactly matches source freeze output.

Requested verification command:

```sh
backend/.venv/bin/pip install -r backend/requirements.txt -r backend/requirements-dev.txt -c backend/constraints.txt
```

Exit 1: pip could not resolve `pypi.org`, exhausted retries for boto3, and reported ResolutionImpossible because it could not fetch pinned boto3 1.43.106. This does not establish a genuine package dependency conflict. Pins were preserved as requested. The worktree currently differs from the snapshot for boto3/botocore (1.43.107 vs 1.43.106), filelock (4.0.9 vs 4.0.8), langsmith (0.14.3 vs 0.14.2), and openai (3.23.0 vs 3.22.1). Test results therefore validate the existing worktree environment, not a successfully synchronized constrained environment.

## Concerns

- macOS constrained installation remains unverified because network/DNS access is unavailable.
- Ubuntu Python 3.12 installation and actual Actions execution remain unverified; GitHub was not touched. No specific package is known to be Linux-incompatible from local inspection. Binary packages such as torch 2.14.1, kiwipiepy 0.24.0, numpy 2.5.3, scipy 1.18.1, and browser dependencies still require actual Linux resolution verification; macOS freeze alone cannot prove compatibility.
- The brief's existing timing-sensitive label test remains unchanged.
