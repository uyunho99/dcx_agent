import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import pytest

from .conftest import SCRIPTS


def test_up_to_date_silent(macmini):
    m = macmini
    m.set_current(m.b)
    assert m.run_deploy() == (0, None)
    assert m.run_deploy(DEPLOY_DRY_RUN="1")[1]["decision"] == "up-to-date"


def test_ci_pending_then_stuck(macmini):
    m = macmini
    m.ci("in_progress", None)
    assert m.run_deploy() == (0, None)
    (m.root / "shared/ci-pending-since").write_text(f"{m.b} {int(time.time()) - 1860}\n")
    assert m.run_deploy()[1]["decision"] == "ci-stuck"
    m.run_deploy()
    assert len(m.logs) == 1


def test_ci_failed_once(macmini):
    m = macmini
    m.ci(conclusion="failure")
    assert m.run_deploy()[1]["decision"] == "ci-failed"
    m.run_deploy()
    assert len(m.logs) == 1 and m.current == m.a
    m.ci(conclusion="failure", attempt=2)
    m.run_deploy()
    assert len(m.logs) == 2


@pytest.mark.parametrize("payload", ["<html>", "", '{"message":"API rate limit exceeded"}', '{"workflow_runs":[{}]}'])
def test_ci_api_garbage(macmini, payload):
    m = macmini
    assert m.run_deploy(FAKE_CI=payload)[1]["decision"] == "ci-unknown"
    assert m.current == m.a


def test_success_deploys(macmini):
    m = macmini
    code, log = m.run_deploy()
    assert code == 0, m.output
    assert log["decision"] == "deployed" and m.current == m.b
    sha, snap = (m.root / "shared/deploy-history").read_text().splitlines()[-1].split()
    assert sha == m.b and (Path(snap) / "sessions/value").read_text() == "original"
    assert (m.root / "restarts").read_text().splitlines() == ["start"]
    assert not (m.root / "shared/deploy-state").exists()


def test_build_failed_marks_and_keeps(macmini):
    m = macmini
    assert m.run_deploy(FAKE_BUILD_FAIL="1")[1]["decision"] == "build-failed"
    assert (m.root / "shared/last-failed-sha").read_text().strip() == m.b
    assert m.current == m.a and not (m.root / f"releases/{m.b}").exists()
    m.run_deploy()
    assert len(m.logs) == 1


def test_unhealthy_rolls_back_with_snapshot(macmini):
    m = macmini
    # Mutate only the candidate's data, preserving evidence when rollback starts.
    m.command("restart", '''import os,pathlib,sys
p=pathlib.Path(os.environ['APP_ROOT'])
if sys.argv[1]=='start' and p.joinpath('current').resolve().name==os.environ['BAD_SHA']:
    (p/'shared/data/sessions/value').write_text('mutated')
    (p/'shared/data/work/runs.sqlite').write_text('work-mutated')
''')
    code, log = m.run_deploy(DCX_FORCE_UNHEALTHY_SHA=m.b, BAD_SHA=m.b)
    assert code != 0 and log["decision"] == "unhealthy" and log["rolled_back_to"] == m.a
    assert m.current == m.a and not (m.root / f"releases/{m.b}").exists()
    assert (m.root / "shared/data/sessions/value").read_text() == "original"
    assert (m.root / "shared/data/work/runs.sqlite").read_text() == "work-before"
    failed = list((m.root / "shared/snapshots").glob(f"*-{m.b}-failed"))
    assert (failed[0] / "sessions/value").read_text() == "mutated"


def test_unhealthy_both(macmini):
    m = macmini
    assert m.run_deploy(FAKE_HEALTH="{}")[1]["decision"] == "unhealthy-both"
    assert (m.root / f"releases/{m.b}").exists()
    assert (m.root / "shared/last-failed-sha").read_text().strip() == m.b


def test_first_deploy_unhealthy(macmini):
    m = macmini
    (m.root / "current").unlink()
    (m.root / "shared/deploy-history").unlink()
    log = m.run_deploy(FAKE_HEALTH="{}")[1]
    assert log["decision"] == "unhealthy" and log["rolled_back_to"] is None


def test_snapshot_keeps_five(macmini):
    m = macmini
    m.lib('for n in 1 2 3 4 5 6 7; do snapshot_sessions "$n"; done')
    assert len(list((m.root / "shared/snapshots").iterdir())) == 5


def test_snapshot_without_sessions(macmini):
    m = macmini
    import shutil
    shutil.rmtree(m.root / "shared/data/sessions")
    assert m.run_deploy()[1]["decision"] == "deployed"
    snap = (m.root / "shared/deploy-history").read_text().splitlines()[-1].split()[1]
    assert not (Path(snap) / "sessions").exists()
    m.lib(f'restore_sessions "{snap}"')
    assert not (m.root / "shared/data/sessions").exists()


def test_prune_keeps_three_plus_current(macmini):
    m = macmini
    for n in range(6):
        (m.root / f"releases/r{n}").mkdir()
    (m.root / "shared/deploy-history").write_text("".join(f"r{n} -\n" for n in range(6)))
    m.lib("prune_releases")
    assert {p.name for p in (m.root / "releases").iterdir()} == {m.a, "r3", "r4", "r5"}


def test_stale_lock_taken(macmini):
    m = macmini
    lock = m.root / "shared/deploy.lock"
    lock.mkdir()
    (lock / "pid").write_text(str(os.getpid()))
    assert m.run_deploy() == (0, None)
    (lock / "pid").write_text("99999999")
    assert m.run_deploy()[1]["decision"] == "deployed"
    assert not lock.exists()


def test_leftover_current_tmp(macmini):
    m = macmini
    (m.root / "current.tmp").symlink_to(f"releases/{m.a}")
    assert m.run_deploy()[1]["decision"] == "deployed"
    assert m.current == m.b


def test_venv_hash_and_cleanup(macmini):
    m = macmini
    m.env["DCX_BUILD_CMD"] = ""
    (m.root / "current").unlink()
    m.lib(f'build_release "{m.a}"; build_release "{m.b}"')
    m.set_current(m.a)
    first = (m.root / f"releases/{m.a}/backend/.venv").resolve()
    assert first == (m.root / f"releases/{m.b}/backend/.venv").resolve()
    assert len((m.root / "pip-calls").read_text().splitlines()) == 1
    assert " -c " in (m.root / "pip-calls").read_text()
    (m.src / "backend/requirements.txt").write_text("example==2\n")
    c = m.commit("C")
    m.git("-C", str(m.src), "push", m.env["DCX_REPO_URL"], "main")
    m.b = c
    m.ci()
    assert m.run_deploy(FAKE_PIP_FAIL="1")[1]["decision"] == "build-failed"
    assert list((m.root / "shared/venvs").iterdir()) == [first]
    (m.root / "shared/last-failed-sha").unlink()
    assert m.run_deploy()[1]["decision"] == "deployed"
    assert (m.root / f"releases/{c}/backend/.venv").resolve() != first


def test_secrets_not_in_build_env(macmini):
    m = macmini
    assert m.run_deploy(OPENAI_API_KEY="sk-test")[0] == 0
    dump = (m.root / f"releases/{m.b}/build-env").read_text()
    assert "sk-test" not in dump and "NEXT_PUBLIC_API_URL" in dump
    assert "sk-test" not in (m.root / "logs/deploy.log").read_text()


def test_runs_on_bash32_syntax(macmini):
    for p in SCRIPTS.glob("*.sh"):
        text = p.read_text()
        assert not re.search(r"declare\s+-A|\bmapfile\b|\$\{[^}]*,,", text)
        subprocess.run([macmini.env["DCX_BASH"], "-n", str(p)], check=True)
    assert (SCRIPTS / "deploy.sh").exists()


def test_stop_snapshot_switch_start_order(macmini):
    m = macmini
    m.command("restart", '''import os,pathlib,sys
p=pathlib.Path(os.environ['APP_ROOT']); phase=sys.argv[1]
snaps=list((p/'shared/snapshots').glob('*/work/runs.sqlite'))
if phase=='stop':
    assert not snaps
    assert p.joinpath('current').resolve().name==os.environ['OLD_SHA']
    (p/'shared/data/work/runs.sqlite').write_text('stopped')
else:
    assert len(snaps)==1 and snaps[0].read_text()=='stopped'
    assert p.joinpath('current').resolve().name==os.environ['NEW_SHA']
with (p/'events').open('a') as f:f.write(phase+'\\n')
''')
    assert m.run_deploy(OLD_SHA=m.a, NEW_SHA=m.b)[0] == 0, m.output
    assert (m.root / "events").read_text().splitlines() == ["stop", "start"]


def test_workers_killed(macmini):
    m = macmini
    program = "import os,pathlib,signal,sys,time; p=pathlib.Path(sys.argv[1])/('alive-'+str(os.getpid())); p.touch(); signal.signal(signal.SIGTERM, lambda *_: (p.unlink(missing_ok=True), sys.exit(0))); time.sleep(120)"
    worker = subprocess.Popen([sys.executable, "-c", program, str(m.root)], cwd=m.root / f"releases/{m.a}/backend", start_new_session=True)
    other = subprocess.Popen([sys.executable, "-c", program, str(m.root)], cwd=m.root, start_new_session=True)
    (m.root / "processes.json").write_text(json.dumps({str(worker.pid): str(m.root / f"releases/{m.a}/backend"), str(other.pid): str(m.root)}))
    try:
        for _ in range(100):
            if all((m.root / f"alive-{p.pid}").exists() for p in (worker, other)):
                break
            time.sleep(.01)
        assert m.run_deploy()[0] == 0, m.output
        worker.wait(timeout=3)
        assert other.poll() is None
    finally:
        for p in (worker, other):
            if p.poll() is None:
                p.kill()
            p.wait()


@pytest.mark.parametrize("healthy", [True, False])
def test_resume_after_crash_mid_switch(macmini, healthy):
    m = macmini
    snap = m.lib(f'snapshot_sessions "{m.b}"')
    m.set_current(m.b)
    (m.root / "shared/deploy-state").write_text(f"switching {m.b} {m.a} {snap}\n")
    code, log = m.run_deploy(DCX_FORCE_UNHEALTHY_SHA="" if healthy else m.b)
    assert log["decision"] == ("deployed" if healthy else "unhealthy")
    assert m.current == (m.b if healthy else m.a)
    assert not (m.root / "shared/deploy-state").exists()
    assert not (m.root / "build-calls").exists()


def test_legacy_release_health(macmini):
    m = macmini
    assert m.lib(f'if wait_healthy 3 "{m.a}"; then echo yes; else echo no; fi', FAKE_HEALTH='{"status":"ok"}') == "yes"
    m.set_current(m.b)
    assert m.lib(f'if wait_healthy 1 "{m.b}"; then echo yes; else echo no; fi', FAKE_HEALTH='{"status":"ok"}') == "no"


def test_frontend_rebuild_on_config_change(macmini):
    m = macmini
    m.lib(f'build_release "{m.b}"; build_release "{m.b}"')
    assert len((m.root / "build-calls").read_text().splitlines()) == 1
    old = (m.root / f"releases/{m.b}/.build-config").read_text()
    (m.root / "shared/runtime.env").write_text("NEXT_PUBLIC_API_URL=http://127.0.0.1:18401\n")
    m.lib(f'build_release "{m.b}"')
    assert len((m.root / "build-calls").read_text().splitlines()) == 2
    assert (m.root / f"releases/{m.b}/.build-config").read_text() != old
    assert m.run_deploy(FAKE_SESSIONS_FAIL="1")[1]["decision"] == "unhealthy-both"


def test_preflight_missing_binary(macmini):
    m = macmini
    (m.bin / "npm").unlink()
    code, log = m.run_deploy()
    assert code != 0 and log["decision"] == "error" and log["missing"] == "npm"
    assert m.current == m.a and not (m.root / "build-calls").exists()


def test_dry_run_does_not_deploy(macmini):
    m = macmini
    assert m.run_deploy(DEPLOY_DRY_RUN="1")[1]["dry_run"] is True
    assert m.current == m.a and not (m.root / "build-calls").exists()


@pytest.mark.parametrize("overrides", [{"FAKE_CURL_EXIT": "22"}, {"FAKE_CI": '{"workflow_runs":null}'}])
def test_ci_transport_and_schema_fail_closed(macmini, overrides):
    m = macmini
    assert m.run_deploy(**overrides)[1]["decision"] == "ci-unknown"
    assert m.current == m.a


@pytest.mark.parametrize("overrides", [{"FAKE_WEB_STATUS": "302"}, {"FAKE_SESSIONS_STATUS": "301"}, {"FAKE_WEB_FAIL": "22"}])
def test_readiness_requires_http_200(macmini, overrides):
    m = macmini
    assert m.lib(f'if wait_healthy 1 "{m.a}"; then echo yes; else echo no; fi', **overrides) == "no"


def test_config_is_data_not_shell(macmini):
    m = macmini
    (m.root / "shared/runtime.env").write_text('NEXT_PUBLIC_API_URL="$(touch injected)"\nSECRET=sk-test\n')
    m.lib(f'build_release "{m.b}"')
    dump = (m.root / f"releases/{m.b}/build-env").read_text()
    assert "sk-test" not in dump and "$(touch injected)" in dump
    assert not (m.root / f"releases/{m.b}/injected").exists()


@pytest.mark.parametrize("service", ["API", "WEB"])
def test_hold_stop_and_start(macmini, owned_listener, service):
    m = macmini
    child, port = owned_listener
    m.env["DCX_" + service + "_PORT"] = port
    m.command("launchctl", "raise AssertionError('deploy must not use launchctl')")
    m.lib('stop_services', DCX_RESTART_CMD="")
    child.wait(timeout=3)
    assert (m.root/"shared/maintenance").exists()
    assert m.lib('listener_pids') == ""
    m.lib('start_services', DCX_RESTART_CMD="")
    assert not (m.root/"shared/maintenance").exists()


@pytest.mark.parametrize("service", ["API", "WEB"])
def test_listener_blocks_snapshot(macmini, owned_listener, service):
    m = macmini
    child, port = owned_listener
    m.env["DCX_" + service + "_PORT"] = port
    # Simulate failed PID identity discovery: termination cannot safely signal it.
    m.command("ps", "pass")
    code, log = m.run_deploy(DCX_RESTART_CMD="")
    assert code != 0 and log["decision"] == "error"
    assert child.poll() is None
    assert (m.root/"shared/maintenance").exists()
    assert not list((m.root/"shared/snapshots").iterdir())
    assert m.current == m.a
    # Recovery must also refuse to release the hold while a writer remains.
    assert m.run_deploy(DCX_RESTART_CMD="")[0] != 0
    assert (m.root/"shared/maintenance").exists()


def test_active_release_without_marker_is_untouched(macmini):
    m = macmini
    live = m.root/"releases"/m.a
    (live/"sentinel").write_text("live")
    assert m.lib(f'if build_release "{m.a}"; then echo rebuilt; else echo refused; fi') == "refused"
    assert (live/"sentinel").read_text() == "live"
    assert not (m.root/"build-calls").exists()


@pytest.mark.parametrize("entry", ["deploy.sh", "dcxctl"])
def test_cache_key_failure_aborts_build(macmini, entry):
    m = macmini
    (m.bin/"python3.12").unlink()
    m.command("python3.12", '''import os,sys
if sys.argv[1:] == ['--version']: sys.exit(42)
os.execv(sys.executable,[sys.executable]+sys.argv[1:])
''')
    args = [m.env["DCX_BASH"], str(SCRIPTS/entry)] + (["deploy"] if entry == "dcxctl" else [])
    r = subprocess.run(args, env=dict(m.env, DCX_BUILD_CMD=""), capture_output=True, text=True, timeout=45)
    assert r.returncode != 0
    assert m.logs[-1]["decision"] == "build-failed"
    assert not list((m.root/"shared/venvs").iterdir())
    assert m.current == m.a


def test_recovery_before_switch_and_history_idempotence(macmini):
    m = macmini
    snap = m.lib(f'snapshot_sessions "{m.b}"')
    (m.root / f"releases/{m.b}").mkdir()
    state = m.root / "shared/deploy-state"
    state.write_text(f"switching {m.b} {m.a} {snap}\n")
    assert m.run_deploy()[1]["decision"] == "deployed"
    state.write_text(f"switching {m.b} {m.a} {snap}\n")
    assert m.run_deploy()[0] == 0
    history = (m.root / "shared/deploy-history").read_text().splitlines()
    assert sum(line.startswith(m.b) for line in history) == 1


def test_resume_interrupted_rollback(macmini):
    m = macmini
    snap = m.lib(f'snapshot_sessions "{m.b}"')
    m.set_current(m.b)
    (m.root / "shared/data/sessions/value").write_text("failed-data")
    # Restoration had completed, but process died before starting the old API.
    m.lib(f'restore_sessions "{snap}"')
    (m.root / "shared/deploy-state").write_text(f"rolling-back {m.b} {m.a} {snap}\n")
    assert m.run_deploy()[1]["decision"] == "unhealthy"
    assert m.current == m.a
    assert (m.root / "shared/data/sessions/value").read_text() == "original"
    assert (Path(snap + "-failed") / "sessions/value").read_text() == "failed-data"


def test_venv_cache_includes_constraints_and_python(macmini):
    m = macmini
    m.env["DCX_BUILD_CMD"] = ""
    m.lib(f'build_release "{m.b}"')
    first = (m.root / f"releases/{m.b}/backend/.venv").resolve()
    (m.src / "backend/constraints.txt").write_text("example==2\n")
    c = m.commit("constraints changed")
    m.git("-C", str(m.src), "push", m.env["DCX_REPO_URL"], "main")
    m.git("-C", str(m.root / "repo"), "fetch", "origin", "main")
    m.lib(f'build_release "{c}"')
    second = (m.root / f"releases/{c}/backend/.venv").resolve()
    assert first != second
    (m.bin / "python3.12").unlink()
    m.command("python3.12", '''import os,sys
if sys.argv[1:] == ['--version']:
    print('Python 3.12.99')
else:
    os.execv(sys.executable, [sys.executable]+sys.argv[1:])
''')
    (m.root / f"releases/{c}/.built").unlink()
    m.lib(f'build_release "{c}"')
    assert (m.root / f"releases/{c}/backend/.venv").resolve() not in (first, second)


def test_rollback_replay_preserves_new_writes(macmini):
    m = macmini
    snap = m.lib(f'snapshot_sessions "{m.b}"')
    m.lib(f'restore_sessions "{snap}"')
    for name, file in [('sessions', 'value'), ('work', 'runs.sqlite')]:
        (m.root/'shared/data'/name/file).write_text('new-write')
    (m.root/'shared/deploy-state').write_text(f'rolling-back {m.b} {m.a} {snap}\n')
    m.run_deploy()
    assert (m.root/'shared/data/sessions/value').read_text() == 'original'
    assert (Path(snap+'-failed-1')/'sessions/value').read_text() == 'new-write'
    assert (Path(snap+'-failed-1')/'work/runs.sqlite').read_text() == 'new-write'
    for _ in range(6):
        m.lib(f'snapshot_sessions "{m.b}"')
    assert (Path(snap+'-failed-1')/'sessions/value').read_text() == 'new-write'


@pytest.mark.parametrize('owner', ['dead', 'live', 'legacy'])
def test_stale_hold_at_up_to_date_tick(macmini, owner):
    m = macmini
    m.set_current(m.b)
    hold = m.root/'shared/maintenance'
    hold.write_text('' if owner == 'legacy' else f'{os.getpid() if owner == "live" else 99999999} install\n')
    assert m.run_deploy()[0] == 0
    assert hold.exists() == (owner == 'live')
    assert [x['decision'] for x in m.logs] == ([] if owner == 'live' else ['hold-cleared'])


def test_hold_records_owner_and_reason(macmini):
    m = macmini
    assert m.lib('stop_services; read -r owner reason < "$MAINTENANCE"; [[ "$owner" == "$$" ]]; echo "$reason"', DCX_HOLD_REASON='install') == 'install'


@pytest.mark.parametrize('port', ['3000', '3310', '3311', '8310', '8311', '3400', '8400'])
@pytest.mark.parametrize('operation', ['listener_pids', 'stop_services', 'terminate_pids ""'])
def test_library_refuses_protected_ports(macmini, port, operation):
    m = macmini
    m.command('lsof', "raise AssertionError('must not inspect protected ports')")
    assert m.lib(f'if {operation}; then echo unsafe; else echo refused; fi', DCX_API_PORT=port) == 'refused'
    assert m.logs[-1]['decision'] == 'error'
    assert not (m.root/'events').exists()


@pytest.mark.parametrize('kind', ['listener', 'worker', 'node'])
def test_late_writer_blocks_snapshot(macmini, kind):
    m = macmini
    # A launch already in flight becomes visible during the settling delay.
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], cwd=m.root/'releases'/m.a/'backend')
    try:
        (m.bin/'sleep').unlink()
        m.command('sleep', "import os,pathlib,sys; assert sys.argv[1:] == ['1']; (pathlib.Path(os.environ['APP_ROOT'])/'late').touch()")
        command = 'node' if kind == 'node' else 'Python'
        m.command('ps', f"""import pathlib,sys
if '-axo' in sys.argv and pathlib.Path({str(m.root/'late')!r}).exists() and {kind!r} != 'listener':
    print('{child.pid} {command}')
""")
        m.command('lsof', f"""import pathlib,sys
if '-p' in sys.argv: print('n{m.root}/releases/{m.a}/backend')
if '-iTCP:18400' in sys.argv and pathlib.Path({str(m.root/'late')!r}).exists() and {kind!r} == 'listener':
    print('{child.pid}')
""")
        code, log = m.run_deploy()
        assert code != 0 and log['decision'] == 'error'
        assert child.poll() is None
        assert m.current == m.a
        assert not list((m.root/'shared/snapshots').iterdir())
    finally:
        child.terminate(); child.wait(timeout=5)


def test_remaining_worker_aborts_before_snapshot(macmini):
    m = macmini
    # A test-owned child is discoverable but has no trusted signal identity.
    import sys, json
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], cwd=m.root/'releases'/m.a/'backend')
    try:
        m.command('ps', f"import sys\nif '-axo' in sys.argv: print('{child.pid} Python')")
        m.command('lsof', f"import sys\nif '-p' in sys.argv: print('n{m.root}/releases/{m.a}/backend')")
        code, log = m.run_deploy()
        assert code != 0 and log['decision'] == 'error'
        assert child.poll() is None
        assert m.current == m.a
        assert not list((m.root/'shared/snapshots').iterdir())
    finally:
        child.terminate(); child.wait(timeout=5)


@pytest.mark.parametrize('kind,location', [('Python', 'repo/backend'), ('node', 'repo/frontend'), ('node', 'releases')])
def test_writer_discovery_includes_manual_repo_and_node(macmini, kind, location):
    import sys
    m = macmini
    cwd = m.root/location
    cwd.mkdir(parents=True, exist_ok=True)
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], cwd=cwd)
    try:
        m.command('ps', f"print('{child.pid} {kind}')")
        m.command('lsof', f"print('n{cwd}')")
        assert m.lib('worker_pids') == str(child.pid)
    finally:
        child.terminate(); child.wait(timeout=5)
