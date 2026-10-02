"""Install tests only render plans; never execute privileged service actions."""
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
    before = (m.root/'shared/runtime.env').read_bytes()
    r = run(m, 'install.sh', '--dry-run', '--output-dir', str(out), *(['--qa'] if qa else []),
            DCX_API_PORT='', DCX_WEB_PORT='')
    assert r.returncode == 0, r.stderr
    api, web = ('8401', '3401') if qa else ('8400', '3400')
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
    runtime = (out/'runtime.env').read_text()
    for value in ('STORAGE=local', 'LABEL_GPT_BACKEND=codex_exec', 'JEV_BACKEND=fake',
                  f'CORS_ORIGINS=http://localhost:{web}', f'NEXT_PUBLIC_API_URL=http://localhost:{api}',
                  f'AUTHOR_SALT_PATH={m.root}/shared/data/.author_salt', f'LOCAL_DATA_DIR={m.root}/shared/data'):
        assert value in runtime
    assert (m.root/'shared/runtime.env').read_bytes() == before
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
