"""Render plans and inject pre-registration failures in temporary roots only."""
import os
import plistlib
import subprocess
import sys
import pytest
from .conftest import SCRIPTS


def run(m, name, *args, input='', **env):
    return subprocess.run([m.env['DCX_BASH'], str(SCRIPTS/name), *args],
                          env=dict(m.env, **env), input=input, text=True, capture_output=True, timeout=45)


def forbid_services(m):
    for name in ('sudo', 'launchctl', 'kill'):
        m.command(name, "raise AssertionError('forbidden service operation')")


@pytest.mark.parametrize('qa', [False, True])
def test_install_dry_run(macmini, tmp_path, qa):
    m = macmini
    forbid_services(m)
    out = tmp_path/'render & space'
    (m.root/'shared/runtime.env').unlink()
    r = run(m, 'install.sh', '--dry-run', '--output-dir', str(out), *(['--qa'] if qa else []),
            DCX_API_PORT='' if qa else '18400', DCX_WEB_PORT='' if qa else '13400')
    assert r.returncode == 0, r.stderr
    api, web = ('8401', '3401') if qa else ('18400', '13400')
    label = 'ai.person-a.dcx-agent' + ('-qa' if qa else '')
    for value in (str(m.root), api, web, '건드리지 않음: 3000 3310 3311 8310 8311',
                  'main 머리 커밋을 정식 빌드해 첫 릴리스로 · 손 clone은 설치 후 삭제', 'AUTHOR_SALT_PATH'):
        assert value in r.stdout
    assert ('Library/LaunchAgents' if qa else '/Library/LaunchDaemons') in r.stdout
    assert len(list(out.glob('*.plist'))) == 3
    for job in ('deploy', 'api', 'web'):
        p = out/f'{label}.{job}.plist'
        assert '__' not in p.read_text()
        d = plistlib.loads(p.read_bytes())
        assert d['Label'] == f'{label}.{job}'
        assert d['EnvironmentVariables']['HOME'] == m.env['HOME']
        assert d['EnvironmentVariables']['APP_ROOT'] == str(m.root)
        assert d['EnvironmentVariables']['DCX_API_PORT'] == api
        assert d['EnvironmentVariables']['DCX_WEB_PORT'] == web
        assert 'DCX_LAUNCH_DOMAIN' not in d['EnvironmentVariables']
        if qa:
            assert 'UserName' not in d
        else:
            assert d['UserName']
        if job == 'deploy':
            assert d['StartInterval'] == 120 and d['RunAtLoad'] is True
        else:
            assert d['KeepAlive'] is True
            assert d['ThrottleInterval'] == 10
        if sys.platform == 'darwin':
            subprocess.run(['/usr/bin/plutil', '-lint', str(p)], check=True, capture_output=True)
    api_url = 'http://localhost:'+api if qa else 'https://dcx-api.person-a.ai'
    cors = 'http://localhost:'+web if qa else 'https://dcx.person-a.ai,http://localhost:'+web
    assert f'NEXT_PUBLIC_API_URL={api_url}' in r.stdout
    assert f'CORS_ORIGINS={cors}' in r.stdout
    runtime = (out/'runtime.env').read_text()
    for value in ('STORAGE=local', 'LABEL_GPT_BACKEND=codex_exec', 'JEV_BACKEND=fake',
                  f'CORS_ORIGINS={cors}', f'NEXT_PUBLIC_API_URL={api_url}',
                  f'AUTHOR_SALT_PATH={m.root}/shared/data/.author_salt', f'LOCAL_DATA_DIR={m.root}/shared/data'):
        assert value in runtime
    assert not (m.root/'shared/runtime.env').exists()
    assert not (m.root/'ops').exists()


@pytest.mark.parametrize('answer', ['n\n', '\n', 'yes\n', ''])
def test_install_declined_no_changes(macmini, tmp_path, answer):
    m = macmini
    forbid_services(m)
    out = tmp_path/'not-created'
    before = {str(p.relative_to(m.root)): p.read_bytes() for p in m.root.rglob('*') if p.is_file()}
    r = run(m, 'install.sh', '--output-dir', str(out), input=answer)
    assert r.returncode == 0, r.stderr
    assert not out.exists()
    assert before == {str(p.relative_to(m.root)): p.read_bytes() for p in m.root.rglob('*') if p.is_file()}


def test_run_commands(macmini):
    m = macmini
    (m.root/'shared/app.env').write_text('OPENAI_API_KEY=do-not-print\n')
    a = run(m, 'run-api.sh', '--print-cmd', DCX_API_PORT='8400')
    w = run(m, 'run-web.sh', '--print-cmd', DCX_WEB_PORT='3400', OPENAI_API_KEY='inherited-secret')
    assert a.returncode == w.returncode == 0, a.stderr+w.stderr
    assert '--host 127.0.0.1 --port 8400' in a.stdout
    assert f'DCX_RELEASE_SHA={m.a}' in a.stdout
    assert '-H 127.0.0.1 -p 3400' in w.stdout
    assert 'OPENAI_API_KEY' not in a.stdout+w.stdout
    assert 'do-not-print' not in a.stdout+w.stdout
    assert 'inherited-secret' not in w.stdout
    assert not (m.root/'shared/api.pid').exists()


def test_web_execution_environment(macmini):
    m = macmini
    frontend = m.root/'releases'/m.a/'frontend'
    (frontend/'node_modules/.bin').mkdir(parents=True)
    next_bin = frontend/'node_modules/.bin/next'
    next_bin.write_text(f'#!{sys.executable}\nimport os,json; print(json.dumps(dict(os.environ)))\n')
    next_bin.chmod(0o755)
    (m.root/'shared/runtime.env').write_text('NEXT_PUBLIC_API_URL=http://localhost:8400\nPRIVATE_RUNTIME=hidden\n')
    r = run(m, 'run-web.sh', OPENAI_API_KEY='inherited-secret')
    assert r.returncode == 0, r.stderr
    import json
    env = json.loads(r.stdout)
    assert env['NEXT_PUBLIC_API_URL'] == 'http://localhost:8400'
    assert env['PORT'] == '13400'
    assert 'OPENAI_API_KEY' not in env and 'PRIVATE_RUNTIME' not in env
    assert (m.root/'shared/web.pid').read_text().strip().isdigit()


def test_install_piped_yes_is_not_interactive(macmini, tmp_path):
    m = macmini
    forbid_services(m)
    out = tmp_path/'not-created'
    r = run(m, 'install.sh', '--output-dir', str(out), input='y\n')
    assert r.returncode != 0
    assert '대화형' in r.stderr
    assert not out.exists()
    assert not (m.root/'ops').exists()


def test_api_execution_environment(macmini):
    m = macmini
    backend = m.root/'releases'/m.a/'backend'
    bin_dir = backend/'.venv/bin'
    bin_dir.mkdir(parents=True)
    import shlex
    (bin_dir/'python').write_text('#!/bin/bash\nexec '+shlex.quote(sys.executable)+' \"$@\"\n')
    (bin_dir/'python').chmod(0o755)
    uvicorn = bin_dir/'uvicorn'
    uvicorn.write_text(f'#!{sys.executable}\nimport os,json; print(json.dumps(dict(os.environ)))\n')
    uvicorn.chmod(0o755)
    (m.root/'shared/runtime.env').write_text(f'AUTHOR_SALT_PATH={m.root}/shared/data/.author_salt\nSTORAGE=local\n')
    r = run(m, 'run-api.sh')
    assert r.returncode == 0, r.stderr
    import json
    env = json.loads(r.stdout)
    assert env['OPENAI_API_KEY'] == 'sk-test'
    assert env['DCX_RELEASE_SHA'] == m.a
    assert env['AUTHOR_SALT_PATH'] == str(m.root/'shared/data/.author_salt')
    assert (m.root/'shared/api.pid').read_text().strip().isdigit()


@pytest.mark.parametrize('script', ['run-api.sh', 'run-web.sh'])
def test_run_waits_during_maintenance(macmini, script):
    m = macmini
    (m.root/'shared/maintenance').touch()
    # Record the required delay without making the suite sleep.
    (m.bin/'sleep').unlink()
    m.command('sleep', "import sys; assert sys.argv[1:] == ['10']")
    r = run(m, script, '--print-cmd')
    assert r.returncode == 0, r.stderr
    assert r.stdout == ''
    assert not (m.root/('shared/'+script[4:-3]+'.pid')).exists()


@pytest.mark.parametrize('qa', [False, True])
def test_assume_yes_only_qa(macmini, qa):
    m = macmini
    # Stop at OS validation, before any filesystem/service installation action.
    (m.bin/'uname').unlink()
    m.command('uname', "print('TestOS')")
    r = run(m, 'install.sh', *(['--qa'] if qa else []), DCX_INSTALL_ASSUME_YES='1')
    if qa:
        assert r.returncode != 0 and 'macOS' in r.stderr
        assert 'y 입력' not in r.stdout
    else:
        assert r.returncode == 0 and 'y 입력' in r.stdout
    assert not (m.root/'ops').exists()


def test_production_assume_yes_still_rejects_piped_y(macmini):
    r = run(macmini, 'install.sh', input='y\n', DCX_INSTALL_ASSUME_YES='1')
    assert r.returncode != 0 and '대화형' in r.stderr


def test_install_failure_clears_own_hold(macmini, tmp_path):
    import shutil
    m = macmini
    if os.geteuid() == 0:
        pytest.skip('QA installer requires a non-root user')
    for name in ('chmod', 'mktemp'):
        (m.bin/name).symlink_to(shutil.which(name))
    (m.bin/'uname').unlink()
    m.command('uname', "print('Darwin')")
    m.command('restart', "import sys; sys.exit(42)")
    m.command('launchctl', "raise AssertionError('must fail before registration')")
    (m.root/'shared/data/.author_salt').write_text('test-salt')
    home = tmp_path/'home'
    home.mkdir()
    existing_urls = 'NEXT_PUBLIC_API_URL=https://operator-api.test\nCORS_ORIGINS=https://operator.test\n'
    (m.root/'shared/runtime.env').write_text(existing_urls)
    r = run(m, 'install.sh', '--qa', HOME=str(home), DCX_INSTALL_ASSUME_YES='1')
    assert r.returncode != 0
    assert not (m.root/'shared/maintenance').exists()
    assert not (m.root/'shared/deploy.lock').exists()
    assert (m.root/'ops').exists(), 'must reach actual installation before injected failure'
    assert not (home/'Library').exists()
    for value in existing_urls.splitlines():
        assert value in (m.root/'shared/runtime.env').read_text()
        assert value in r.stdout


@pytest.mark.parametrize('qa', [False, True])
@pytest.mark.parametrize('override', [False, True])
def test_install_public_url_overrides(macmini, tmp_path, qa, override):
    m = macmini
    forbid_services(m)
    (m.root/'shared/runtime.env').unlink()
    out = tmp_path/'render'
    r = run(m, 'install.sh', '--dry-run', '--output-dir', str(out),
            *(['--qa'] if qa else []), DCX_API_PORT='', DCX_WEB_PORT='',
            HOME=str(m.root.parent), APP_ROOT=str(m.root.parent/'srv/dcx-agent'),
            DCX_PUBLIC_API_URL='https://api.example.test' if override else '',
            DCX_PUBLIC_WEB_URL='https://web.example.test' if override else '')
    assert r.returncode == 0, r.stderr
    api = 'http://localhost:8401' if qa else 'https://api.example.test'
    cors = 'http://localhost:3401' if qa else 'https://web.example.test,http://localhost:3400'
    if not qa and not override:
        api = 'https://dcx-api.person-a.ai'
        cors = 'https://dcx.person-a.ai,http://localhost:3400'
    for value in (f'NEXT_PUBLIC_API_URL={api}', f'CORS_ORIGINS={cors}'):
        assert value in r.stdout
        assert value in (out/'runtime.env').read_text()


@pytest.mark.parametrize('qa', [False, True])
@pytest.mark.parametrize('cors', ['https://operator.test,http://localhost:9999', ''])
def test_install_existing_public_urls_preserved(macmini, tmp_path, qa, cors):
    m = macmini
    forbid_services(m)
    runtime = m.root/'shared/runtime.env'
    original = f"export NEXT_PUBLIC_API_URL = 'https://operator-api.test' # keep\nCORS_ORIGINS='{cors}'\n"
    runtime.write_text(original)
    out = tmp_path/'render'
    r = run(m, 'install.sh', '--dry-run', '--output-dir', str(out), *(['--qa'] if qa else []),
            DCX_PUBLIC_API_URL='https://ignored-api.test', DCX_PUBLIC_WEB_URL='https://ignored-web.test')
    assert r.returncode == 0, r.stderr
    import shlex
    rendered = dict(line.split('=', 1) for line in (out/'runtime.env').read_text().splitlines())
    for key, value in [('NEXT_PUBLIC_API_URL', 'https://operator-api.test'), ('CORS_ORIGINS', cors)]:
        assert shlex.split(rendered[key]) == [value]
        assert f'{key}={value}' in r.stdout
    assert runtime.read_text() == original


@pytest.mark.parametrize('ports', [('18400', '13400'), ('', '')])
def test_agent_dry_run(macmini, tmp_path, ports):
    m = macmini
    forbid_services(m)
    (m.root/'shared/runtime.env').unlink()
    agent = tmp_path/'agent'
    daemon = tmp_path/'daemon'
    env = dict(DCX_API_PORT=ports[0], DCX_WEB_PORT=ports[1])
    if not ports[0]:
        env.update(HOME=str(tmp_path/'home'), APP_ROOT=str(tmp_path/'home/srv/dcx-agent'))
    r = run(m, 'install.sh', '--agent', '--dry-run', '--output-dir', str(agent), **env)
    assert r.returncode == 0, r.stderr
    assert 'Library/LaunchAgents' in r.stdout and '/Library/LaunchDaemons' not in r.stdout
    d = run(m, 'install.sh', '--dry-run', '--output-dir', str(daemon), **env)
    assert d.returncode == 0, d.stderr
    assert len(list(agent.glob('*.plist'))) == 3
    for job in ('deploy', 'api', 'web'):
        name = f'ai.person-a.dcx-agent.{job}.plist'
        actual = plistlib.loads((agent/name).read_bytes())
        expected = plistlib.loads((daemon/name).read_bytes())
        expected.pop('UserName')
        assert actual == expected
        assert actual['Label'] == f'ai.person-a.dcx-agent.{job}'
    for name in ('runtime.env', 'launch.env'):
        assert (agent/name).read_bytes() == (daemon/name).read_bytes()
    assert 'NEXT_PUBLIC_API_URL=https://dcx-api.person-a.ai' in (agent/'runtime.env').read_text()
    launch = (agent/'launch.env').read_text()
    assert f'DCX_API_PORT={ports[0] or "8400"}' in launch
    assert f'DCX_WEB_PORT={ports[1] or "3400"}' in launch
    assert not (m.root/'ops').exists()


def test_agent_qa_usage_error(macmini):
    forbid_services(macmini)
    r = run(macmini, 'install.sh', '--agent', '--qa')
    assert r.returncode == 2
    assert '[--agent|--qa]' in r.stderr


@pytest.mark.parametrize('answer', ['', 'y\n'])
def test_agent_requires_interactive_confirmation(macmini, answer):
    forbid_services(macmini)
    r = run(macmini, 'install.sh', '--agent', input=answer, DCX_INSTALL_ASSUME_YES='1')
    assert 'y 입력' in r.stdout
    if answer:
        assert r.returncode == 1 and '대화형' in r.stderr
    else:
        assert r.returncode == 0
    assert not (macmini.root/'ops').exists()


def test_agent_refuses_sudo(macmini):
    forbid_services(macmini)
    r = run(macmini, 'install.sh', '--agent', SUDO_USER='test-operator')
    assert r.returncode == 1
    assert '운영 에이전트 설치는 sudo 없이 실행하세요' in r.stderr
    assert not (macmini.root/'ops').exists()


@pytest.fixture(autouse=True)
def isolated_launch_registration(macmini, tmp_path):
    # Keep every installer test away from the host's registration directories.
    macmini.env.update(DCX_DAEMON_DIR=str(tmp_path/'Library/LaunchDaemons'),
                       DCX_AGENT_DIR=str(tmp_path/'Library/LaunchAgents'))
    macmini.command('launchctl', "import sys; assert sys.argv[1] == 'print'; sys.exit(1)")


@pytest.mark.parametrize('agent', [True, False])
@pytest.mark.parametrize('source', ['plist', 'registered'])
@pytest.mark.parametrize('job', ['deploy', 'api', 'web'])
def test_install_transition_guard(macmini, tmp_path, agent, source, job):
    m = macmini
    forbid_services(m)
    m.command('launchctl', "import sys; assert sys.argv[1] == 'print'; sys.exit(1)")
    label = f'ai.person-a.dcx-agent.{job}'
    domain = 'system' if agent else f'gui/{os.getuid()}'
    if source == 'plist':
        directory = tmp_path/'Library'/('LaunchDaemons' if agent else 'LaunchAgents')
        directory.mkdir(parents=True)
        (directory/f'{label}.plist').touch()
    else:
        m.command('launchctl', f"import sys; assert sys.argv[1] == 'print'; sys.exit(0 if sys.argv[2] == {f'{domain}/{label}'!r} else 1)")
    before = {str(p.relative_to(m.root)): p.read_bytes() for p in m.root.rglob('*') if p.is_file()}
    out = tmp_path/'not-created'
    r = run(m, 'install.sh', *(['--agent'] if agent else []), '--output-dir', str(out))
    assert r.returncode == 1, r.stderr
    kind = 'LaunchDaemon' if agent else 'LaunchAgent'
    command = ('sudo launchctl bootout system/ai.person-a.dcx-agent.$job; '
               'sudo rm -f /Library/LaunchDaemons/ai.person-a.dcx-agent.$job.plist' if agent else
               'launchctl bootout gui/$(id -u)/ai.person-a.dcx-agent.$job; '
               'rm -f ~/Library/LaunchAgents/ai.person-a.dcx-agent.$job.plist')
    assert r.stderr == (f'운영 {kind}이 아직 등록돼 있습니다. 아래를 터미널에서 실행한 뒤 다시 설치하세요.\n'
                        f'for job in deploy api web; do {command}; done\n')
    assert 'y 입력' not in r.stdout
    assert not out.exists() and not (m.root/'ops').exists()
    assert before == {str(p.relative_to(m.root)): p.read_bytes() for p in m.root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('mode', ['--agent', '--qa', 'daemon'])
def test_install_destination_override(macmini, tmp_path, mode):
    forbid_services(macmini)
    r = run(macmini, 'install.sh', *([] if mode == 'daemon' else [mode]),
            '--dry-run', '--output-dir', str(tmp_path/'render'))
    assert r.returncode == 0, r.stderr
    directory = tmp_path/'Library'/('LaunchDaemons' if mode == 'daemon' else 'LaunchAgents')
    assert f'등록 위치: {directory}\n' in r.stdout


def test_clean_agent_reaches_prompt(macmini):
    forbid_services(macmini)
    macmini.command('launchctl', "import sys; assert sys.argv[1] == 'print'; sys.exit(1)")
    r = run(macmini, 'install.sh', '--agent')
    assert r.returncode == 0, r.stderr
    assert 'y 입력' in r.stdout and r.stderr == ''
    assert not (macmini.root/'ops').exists()
