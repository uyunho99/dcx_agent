# Task T01 report

Status: BLOCKED (implementation and tests complete; dependency installation blocked by network DNS, and requested commit blocked by filesystem permissions).

## Implemented

- Added all 21 stage 3–5 settings using the brief's exact defaults and backend enum values. `JEVMODEL_API_KEY` parses a comma-separated list, trims whitespace, and ignores empty entries. Added the new environment names with empty values to `.env.example`; empty new-stage values use their documented defaults without changing legacy empty-setting behavior.
- Preserved `pinecone_api_key`, `pinecone-client`, and the stage 0–2 `llm_backend="openai_api"` default as instructed. Omitted the Pinecone-removal assertion.
- Added `kiwipiepy`, `torch`, and `scipy` requirements; `numpy` already existed. TensorFlow was already absent from requirements, so no removal diff was necessary.
- Added shared PID detection with nonpositive PID rejection and the prescribed ProcessLookupError/PermissionError behavior. The crawler control, crawler queue, and Codex executor now import that function under their existing names. Crawler `_live` and `_spawn` are unchanged.
- Added persistent `data/work/{sid}/runs.sqlite` run storage. Launch deduplication uses `(sid, version, kind, labeler)` and performs check, spawn, and registration under one `BEGIN IMMEDIATE` transaction. The child uses the same absolute data root and run ID. Failed spawns roll back; successful child processes are reaped in the background.
- Added detached `python -m app.work.worker` launches, public status projection, PID/60-second heartbeat interruption detection, and durable pause/resume/stop requests. Paused live runs also deduplicate. Terminal/interrupted runs cannot be revived by late heartbeats or completion writes.
- Added the callable `KINDS` registry and Context containing sid/version/kind/args/run ID. Cooperative heartbeat checkpoints implement pause/resume and stop; a background thread maintains the ten-second heartbeat even while a kind is blocked in work. Exceptions become durable failed states with exception type only, avoiding credential/document leakage.
- Added a test-only cooperative three-second worker and real subprocess integration tests. Test registration is injected into test subprocesses; production code does not import tests or arbitrary requested modules.

## Files changed

- `.env.example`
- `backend/requirements.txt`
- `backend/app/config.py`
- `backend/app/crawl/control.py`
- `backend/app/crawl/queue.py`
- `backend/app/llm/codex_exec.py`
- `backend/app/work/__init__.py`
- `backend/app/work/proc.py`
- `backend/app/work/status.py`
- `backend/app/work/runner.py`
- `backend/app/work/worker.py`
- `backend/tests/fakes/fake_worker.py`
- `backend/tests/work/test_proc.py`
- `backend/tests/work/test_runner.py`
- `.superpowers/sdd/03-plan/task-T01-report.md` (this ignored local report; not staged)

No files under `docs/development/**` were changed. Initial git status was clean; no existing user changes were overwritten. No push was performed.

## TDD evidence

### Required RED

Wrote the named tests and fake worker before creating `app/work` or changing production code.

Command:

```sh
cd backend && .venv/bin/python -m pytest tests/work -q
```

Failing output excerpt (exit 2):

```text
ERROR collecting tests/work/test_proc.py
from app.work.proc import pid_alive
E   ModuleNotFoundError: No module named 'app.work'
ERROR collecting tests/work/test_runner.py
from app.work import runner
E   ModuleNotFoundError: No module named 'app.work'
2 errors during collection
```

Expected reason: the requested common-worker package and PID helper did not yet exist. Included all six named tests from the brief, applying the controller's Pinecone assertion override, plus PID error semantics coverage.

### Initial GREEN

Same command after the minimum implementation:

```text
7 passed, 1 warning in 8.31s
```

### Additional RED: blank example settings

Command:

```sh
cd backend && .venv/bin/python -m pytest tests/work/test_runner.py::test_empty_example_settings_use_defaults -q
```

Failing output excerpt (exit 1):

```text
ValidationError: 2 validation errors for Settings
embed_dim
  Input should be a valid integer ... input_value=''
jev_backend
  Input should be 'http' or 'fake' ... input_value=''
1 failed, 1 warning in 0.04s
```

Expected reason: copying the required blank example entries would otherwise override typed defaults with empty strings. Added a validator limited to the new stage settings.

### Final focused GREEN / refactor verification

Command:

```sh
cd backend && .venv/bin/python -m pytest tests/work -q
```

Output:

```text
15 passed, 1 warning in 20.27s
```

Coverage includes concurrent duplicate start, killed worker, independent labelers, pause/resume, PID aliases/error semantics, defaults/CSV keys, stopping a paused worker and restarting, failure persistence, version independence, stale heartbeat fencing, spawn rollback, unknown-kind failure, real ten-second background heartbeat, and blank example settings. Moved the shared PID aliases into each existing module's import section during refactoring.

## Full backend suite

Command (run once after the final code changes):

```sh
cd backend && .venv/bin/python -m pytest -q
```

Result (exit 0):

```text
830 passed, 2 warnings in 98.47s (0:01:38)
```

All 815 baseline tests plus 15 new tests passed. Warnings: existing Pydantic class-based Config deprecation and joblib physical-core detection falling back to logical cores.

## Dependency installation

Ran the controller's exact command against the existing Python 3.12 venv (did not recreate it):

```sh
backend/.venv/bin/pip install -r backend/requirements.txt
```

Result: exit 1 after retries. Relevant output:

```text
NameResolutionError: ... Failed to resolve 'pypi.org'
ERROR: Could not find a version that satisfies the requirement kiwipiepy (from versions: none)
ERROR: No matching distribution found for kiwipiepy
```

This is an index connectivity failure, not evidence that Kiwi has no compatible distribution. Installed package inspection: numpy 2.5.3 and scipy 1.18.1 are present; kiwipiepy and torch are not installed. The macOS Torch wheel's CPU execution could not be verified. No frontend installation was needed or attempted because the controller replaced the original setup instruction and T01 does not change frontend files.

## Self-review findings

- Verified the SQLite write lock spans lookup/launch/registration, including simultaneous starts, and the child cannot heartbeat before registration commits.
- Verified labeler and version separation, correct absolute data-root propagation, and paused-run deduplication.
- Verified stale/interrupted runs are fenced from late heartbeat and terminal writes, and exceptions remain visible as failed status without recording potentially sensitive exception text.
- Verified legacy PID names refer to the identical shared function and only imports/deleted duplicate helpers changed in the three existing lifecycle modules.
- Found and fixed empty-new-setting validation failure through a separate RED/GREEN cycle.
- `git diff --check` passed.
- Kept production kind implementations out of this foundation task. Later stage modules must register their handlers in `KINDS` in the worker process. Unknown kinds fail durably.

## Concerns / limits

- Dependency installation remains incomplete due to the environment's DNS/network restriction. Re-run the documented install command when PyPI is reachable, then verify Kiwi import and Torch CPU operation. The new worker tests do not depend on these packages and cannot validate them.
- Pause and stop are cooperative: handlers must use Context checkpoints and honor `should_stop()`. A blocking handler can remain alive while a stop request is pending; the background heartbeat reports its actual liveness. Stop maps to `interrupted` because the public state contract has no stopped state.
- Existing Pydantic class-based Config deprecation warnings remain; changing the legacy settings configuration style was outside T01.


## Commit attempt and final repository state

Attempted to stage the 14 implementation/test/configuration files and commit with the exact requested subject and trailer:

```text
feat(work): 공용 긴 작업 워커, 3~5단계 설정, torch·kiwi·scipy 추가·tensorflow 제거, pid 확인 통합

Co-Authored-By: Codex <noreply@openai.com>
```

Both `git add` and `git commit` exited 128:

```text
fatal: Unable to create '/Users/persona1/Desktop/dcx_agent/.git/worktrees/dcx_agent-dcx2-stage3-5/index.lock': Operation not permitted
```

The linked worktree's Git metadata lives outside the authorized writable directory. The active approval policy does not permit escalation. No commit was created and nothing was pushed; implementation files remain in the requested worktree for the controller to stage and commit from an environment with access to that metadata. This report is saved at the requested ignored local path.
