# T2 — Mac mini deploy poller

Status: implemented and verified on macOS with `/bin/bash` 3.2.57. No changes were staged or committed in the working repository. No agents were dispatched.

## Files

- `ops/macmini/env.sh`: production defaults, explicit test PATH override, ports, repository and health URLs, stable author salt path, user-agent launchd domain and labels.
- `ops/macmini/lib.sh`: JSON file logging, preflight, lock ownership and stale-lock recovery, portable hashing and atomic rename, isolated release builds, venv caching, snapshots and restoration, service/worker termination, health checks, CI parsing, release pruning.
- `ops/macmini/deploy.sh`: CI decisions, silent polling, dry run, SHA override, release deployment, automatic rollback and persistent crash recovery.
- `backend/tests/ops/conftest.py`: temporary deployment root, two-commit local bare repository, fake command inventory, executable build/restart/pip hooks, deploy and library helpers.
- `backend/tests/ops/test_deploy.py`: 38 deploy tests, including the requested scenarios and additional recovery, HTTP readiness, configuration parsing, service sequencing and cache identity cases.
- This report.

T1-owned implementation and tests were not edited. The permitted empty `backend/tests/ops/__init__.py` was ensured only if absent.

## RED / GREEN evidence

RED, before any deployment scripts existed:

```sh
backend/.venv/bin/python -m pytest backend/tests/ops/test_deploy.py -q -p no:cacheprovider
```

Result: **28 failed**, 1 existing warning, 4.47 seconds. Tests failed because the deployment scripts/functions did not exist.

The initial implementation run produced 13 failures and 15 passes. The failures exposed this execution sandbox's prohibition on `ps`. Process discovery was changed in the test harness to fake `ps`/`lsof` records restricted to test-created PIDs. The worker test still starts actual detached Python processes, terminates its release worker through the production termination function, and proves its outside-root process survives. The next deploy run passed all 28 tests.

After additional checks, the ops suite passed 44 tests. Final verification after all implementation changes and the additional cache-identity test:

```sh
backend/.venv/bin/python -m pytest backend/tests/ops -q -p no:cacheprovider
```

Result: **45 passed**, 1 existing warning, 59.92 seconds. Includes all 7 T1 ops tests present at execution; none were ignored.

```sh
DCX_BASH=/bin/bash backend/.venv/bin/python -m pytest backend/tests/ops/test_deploy.py -q -p no:cacheprovider
```

Result: **38 passed**, 1 existing warning, 58.32 seconds. `/bin/bash --version` reported GNU Bash 3.2.57 on arm64 Apple Darwin. Shell syntax checks are also covered by the suite.

The warning is the existing Pydantic class-based configuration deprecation in `backend/app/config.py`.

## Engineering-review corrections

| Correction | Implementation and evidence |
| --- | --- |
| F1 | Releases are built from Git archives with new hash-addressed venvs; no existing clone/venv is relocated. Health responses without `release` are accepted only for the first SHA in deployment history and only with `status == ok`. The legacy-health test rejects that response for other releases. First-install migration and history seeding remain T3 responsibilities. |
| F2 | Build first, then disable both launchd jobs, terminate their owned service processes, discover and terminate detached workers, snapshot, atomically switch, enable/start. Rollback stops services and workers before restoring data. Restart hooks receive separate `stop` and `start` arguments. Tests assert snapshot data is captured after stop and current has changed before start. |
| F3 | Worker discovery selects Python processes whose physical cwd lies under this APP_ROOT's releases directory. Service descendants and configured port owners are handled separately. Each fixed PID set receives TERM, up to 20 seconds of waiting, then KILL; PID start-time checks avoid killing replacements. A final exit wait prevents snapshotting while a killed writer still exists. The test kills only processes it starts and checks an outside-release process remains alive. |
| F4 | Snapshots and restoration include both `sessions/` and `work/`, preserving symlinks and file metadata. Missing folders are valid empty state. Failed data is retained in `<snapshot>-failed/`; rollback recovery preserves the first failed-data backup. Models, large files and caches outside those two directories are not restored. |
| F5 | Atomic `deploy-state` records include the required `switching <sha> <previous> <snapshot>` state, written before the current-link change. Startup handles it before fetch or up-to-date checks. Additional `preparing` and `rolling-back` states recover interrupted stopping and restoration. Healthy recovery appends history only once; unhealthy recovery restores the previous code and data. Tests cover both outcomes, a crash before the link swap, duplicate finalization and interrupted rollback. |
| F6 | Production PATH defaults to `/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin`. Deploy preflight checks `node npm python3.12 codex git curl`, logs the missing binary and exits before deployment changes. `DCX_PATH` provides hermetic fake-command PATH in tests. macOS lsof falls back to `/usr/sbin/lsof`, which is outside that required PATH. Installer preflight and actual launchd `codex --version` QA belong to T3. |
| F7 | T1-owned health response tests were untouched; the final complete ops run includes and passes T1's current tests. |
| F8 / R1 | Venv cache key hashes requirements, constraints and `python3.12 --version`. Installation passes both `-r` and `-c`. Incomplete environments are removed before use; failed creation/installation removes the new environment and failed release. Tests verify same-input reuse, requirements changes, constraints changes, interpreter-version changes and cleanup after installation failure. Constraint contents remain owned by T1. |
| F9 | `env.sh` exports the stable default `AUTHOR_SALT_PATH=$APP_ROOT/shared/data/.author_salt`. T3 must persist this value in generated runtime.env; T2 does not modify demo data or existing servers. |
| F10 | Public runtime configuration is parsed as data, never sourced as shell. Its sorted `NEXT_PUBLIC_*` values determine `.build-config`; changed values rebuild an inactive cached release. Readiness requires matching health identity plus exact HTTP 200 from `/sessions` and the web URL; redirects fail readiness. Tests exercise cache invalidation, sessions failure and non-200 web/session responses. |
| F11 | `DCX_FORCE_UNHEALTHY_SHA` affects only that SHA, allowing the previous release to pass rollback health checks. The full deploy suite ran explicitly with real macOS `/bin/bash` 3.2. User-agent domain/label overrides support T3's QA setup; no actual launchd jobs were changed during T2. |

## Contracts and implementation notes for T3

- Source `env.sh` before `lib.sh`. Public functions match the T2 brief, with `release` as the lock-release trap handler.
- `log <decision> [extra-json]` appends one JSON line directly to `logs/deploy.log`. Extra fields may be a JSON object or the specified comma-separated JSON fields. Logging does not require stdout capture.
- `DCX_BUILD_CMD`, `DCX_RESTART_CMD` and `DCX_PIP_CMD` are executable paths. Build receives the SHA as argument 1 and runs in the release directory. Restart receives `stop` or `start`. Pip receives `install -r ... -c ...`.
- `restart_services` without arguments performs both phases; `restart_services stop` and `restart_services start` permit snapshot/restore/switch work between them. Manual rollback must use those separate phases.
- `snapshot_sessions` prints only its snapshot directory. History records are `<sha> <snapshot-directory>`; the install baseline may use `<sha> -`.
- Production builds use an environment allowlist plus public runtime values; app.env is never sourced and its release symlink is created only after building. The build test proves even an inherited `OPENAI_API_KEY=sk-test` is absent from the build environment and JSON log.
- Normal up-to-date, known-failed and pending ticks are silent. CI failure reports deduplicate by SHA, run ID and attempt; stuck reports occur once after 30 minutes. CI garbage, schema mismatches and transport errors fail closed.
- Dry-run success uses the permitted decision `deployed` with `dry_run: true`, without building, stopping or switching. Other dry-run decisions use the brief's allowed vocabulary.
- Release pruning retains the last three history entries plus current. Snapshot pruning retains five ordinary snapshots and preserves failed-data evidence separately.

## Concerns and limits

- Linux execution is pending CI. Linux-specific atomic rename and process-cwd inspection are implemented, but were not executed on this macOS host.
- No real launchd, network, npm installation, server, or live worker inventory was exercised. Those integration checks belong to T3/QA. Tests use fake commands, local Git repositories, temporary APP_ROOTs, and no listening sockets; protected deployments and ports were untouched.
- The default production service-control branch is exercised with fake launchctl/port discovery. The sandbox prohibits native ps, so worker-discovery tests use a fake inventory while signal delivery uses real test-owned processes.
- A currently running release is not rebuilt in place. Up-to-date polling remains silent as required; public configuration changes should be deployed with a new commit, or applied when rebuilding an inactive release. This preserves the atomic-release guarantee.
- Rollback restores code, sessions and work databases only. It does not rewind other caches/models/large artifacts. Failed-data backups are deliberately retained and may require operator cleanup over time.
- The broader backend/frontend suites were not run; the requested complete ops suite passed. T1's concurrent files were not modified.

## Fix round 1

T2/T3 findings addressed together. These notes supersede the launchctl service-control and manual-rollback concerns in the original T2/T3 reports. No changes were staged or committed in the working repository; no agents were dispatched. No protected deployment folders, launchd registrations, or existing servers/ports were touched.

### Changes by finding

1. **Non-root LaunchDaemon service control:** `ops/macmini/env.sh:16` defines `MAINTENANCE=$SHARED/maintenance`. `run-api.sh:7` and `run-web.sh:7` check it before resolving current, printing a command, loading configuration, or starting a server; when held, they sleep 10 seconds and exit 0. Both service plists retain KeepAlive and ThrottleInterval=10. `lib.sh:280` adds listener discovery and `lib.sh:290` asserts that both configured ports and release workers are empty. `lib.sh:299` creates the hold, terminates trusted PID-file processes/descendants, port listeners, then detached release Python workers using the existing TERM/20-second/KILL routine, and finally asserts quiescence. Failure retains the hold and prevents snapshot/switch. `lib.sh:332` removes the hold; KeepAlive retries sleeping holders within approximately 10 seconds. `deploy.sh:40` also revalidates stopping before clearing a hold during preparing-state recovery. All launchctl calls were removed from lib/deploy/dcxctl, and DCX_LAUNCH_DOMAIN was removed from runtime configuration/plists. Domain selection now belongs only to install.sh registration. `install.sh:166` releases the hold after bootstrap and before health checks. README operating notes at `ops/macmini/README.md:51` explain both production and QA behavior and replace the permission concern.
2. **Live release without `.built`:** `lib.sh:134` now rejects rebuilding current regardless of marker existence, preserving its files. The cache test builds A while inactive rather than depending on the unsafe previous behavior. `test_deploy.py:323` proves a live sentinel survives and the build hook is never invoked.
3. **Pipeline failures:** `deploy.sh:2` and `dcxctl:2` already had `set -Eeuo pipefail`; these remain enabled. `lib.sh:152` additionally scopes pipefail over the entire venv-key pipeline, so library callers without pipefail also cannot accept a hash of incomplete input. `test_deploy.py:333` injects a failing interpreter-version command through both entrypoints and verifies build failure, an unchanged current, and no cached venv.
4. **Manual rollback crash recovery:** `lib.sh:411` shares atomic state serialization and `lib.sh:417` shares rollback execution/finalization. `dcxctl:57` selects manual mode and writes `rolling-back <from> <to> <snapshot>` before changing failure markers, services, data, or current. An optional second line records `manual` so replay after history finalization still knows the transaction type; existing one-line automatic state remains supported. `deploy.sh:30` resumes it before fetch/CI/up-to-date handling. Manual history removal uses an atomic rename and only removes the matching failed SHA, making replay idempotent. `test_dcxctl.py:88` SIGKILLs the test-owned rollback shell after restore and before history update, verifies next-tick completion, preserved failed-data backup and failed SHA, then replays the state after history finalization to prove no extra row is removed.

### TDD and verification

Tests were written and run before implementation changes:

- `backend/.venv/bin/python -m pytest backend/tests/ops -q -p no:cacheprovider -k 'hold_stop or listener_blocks or active_release_without or cache_key_failure or run_waits or manual_rollback_recovers or install_dry_run'` → **6 failed, 2 passed, 61 deselected, 4 errors**, 6.77s. The two pre-existing pipefail behaviors passed. The four fixture errors were sandbox-denied socket binds (`PermissionError: [Errno 1] Operation not permitted`), not production-script failures.
- After replacing socket binding with a simulated listener inventory backed by real test-owned child processes: `backend/.venv/bin/python -m pytest backend/tests/ops/test_deploy.py -q -p no:cacheprovider -k 'hold_stop or listener_blocks'` → **4 failed, 40 deselected**, 5.85s. This established RED for stop/start and snapshot refusal on both API and web ports.
- Initial implementation run of the complete ops suite → **2 failed, 71 passed**, 95.48s. Fixed the manual rollback error trap overwriting `unhealthy-both`; increased the existing positive legacy-health test timeout from 1 to 3 seconds to avoid shell SECONDS-boundary flakiness.
- `backend/.venv/bin/python -m pytest backend/tests/ops -q -p no:cacheprovider` → **73 passed, 1 warning**, 91.75s.
- `DCX_BASH=/bin/bash backend/.venv/bin/python -m pytest backend/tests/ops -q -p no:cacheprovider` → **73 passed, 1 warning**, 95.46s.
- `backend/.venv/bin/python -m pytest backend/tests -q -p no:cacheprovider` → **1580 passed, 1 deselected, 2 warnings**, 243.15s. The existing `backend/pytest.ini:5` default (`-m "not perf"`) deselects one performance test. Warnings: existing Pydantic class-based config deprecation and sandbox-related joblib physical-core detection fallback.
- `/bin/bash --version` → **3.2.57(1)-release (arm64-apple-darwin25)**. `/bin/bash -n` for every shell entrypoint and AST parsing of embedded Python blocks → **PASS**. `git diff --check` → **PASS**.

`backend/tests/ops/conftest.py:166` limits simulated listener discovery to a child started by that fixture. `test_deploy.py:292` proves stop leaves no reported listener and start removes the hold; `test_deploy.py:306` prevents snapshots/current switches if the child remains, including on the next recovery tick. `test_install.py:145` proves both run scripts exit without producing a server command under the hold. Tests never discover or signal existing server processes.

### Remaining validation limits

Native socket binding and native process inventory are restricted by this sandbox. Listener/worker discovery therefore uses controlled fake inventories; termination and rollback SIGKILL use real test-owned processes. Real launchd retries, login-free boot, privileged installation, and Linux execution remain separate integration/CI checks. No sudoers or other permission workaround is required by the new runtime contract. The existing rollback limit remains: only code and sessions/work are restored, not large artifacts/models/caches.
