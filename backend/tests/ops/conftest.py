"""Hermetic deploy harness: local Git, temporary roots, no listening servers."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "ops/macmini"


class Macmini:
    def __init__(self, root):
        self.root = root / "app"
        self.bin = root / "bin"
        self.bin.mkdir()
        self.root.mkdir()
        self.env = dict(os.environ, APP_ROOT=str(self.root), DCX_BASH=os.getenv("DCX_BASH", "/bin/bash"))
        # Enumerate allowed binaries; never fall through to real curl/launchctl/npm.
        for name in ("bash", "git", "tar", "mkdir", "rm", "mv", "cp", "ln", "cat", "date", "basename", "dirname", "readlink", "awk", "tail", "head", "sort", "sed", "tr", "diff", "sleep", "uname", "shasum", "sha256sum", "id", "touch", "env"):
            source = shutil.which(name)
            if source:
                (self.bin / name).symlink_to(source)
        (self.bin / "python3.12").symlink_to(sys.executable)
        self.env.update(DCX_PATH=str(self.bin), PATH=str(self.bin), DCX_CI_API="https://fake.invalid/runs", DCX_HEALTH_API="http://fake.invalid/health", DCX_HEALTH_WEB="http://fake.invalid/web", DCX_HEALTH_TIMEOUT="3", DCX_API_PORT="18400", DCX_WEB_PORT="13400")
        self.command("curl", '''import json, os, sys
url = sys.argv[-1]
e = os.environ
if url.startswith(e['DCX_CI_API']):
    print(e.get('FAKE_CI', '{}')); sys.exit(int(e.get('FAKE_CURL_EXIT', '0')))
root = e['APP_ROOT']
try: sha = os.path.basename(os.readlink(root + '/current'))
except OSError: sha = ''
if url.endswith('/sessions'):
    print(e.get('FAKE_SESSIONS_STATUS', '200')); sys.exit(int(e.get('FAKE_SESSIONS_FAIL', '0')))
if url == e['DCX_HEALTH_WEB']:
    print(e.get('FAKE_WEB_STATUS', '200')); sys.exit(int(e.get('FAKE_WEB_FAIL', '0')))
value = e.get('FAKE_HEALTH_' + sha, e.get('FAKE_HEALTH', 'auto'))
print(json.dumps({'status':'ok', 'release':sha}) if value == 'auto' else value)
''')
        self.command("build", '''import os, pathlib, sys
p = pathlib.Path(os.environ['APP_ROOT'])
r = p / 'releases' / sys.argv[1]
r.mkdir(parents=True, exist_ok=True)
(r/'BUILT').write_text('yes')
(r/'build-env').write_text(str(dict(os.environ)))
with (p/'build-calls').open('a') as f: f.write(sys.argv[1]+'\\n')
sys.exit(int(os.environ.get('FAKE_BUILD_FAIL', '0')))
''')
        self.command("restart", '''import os, pathlib, sys
p = pathlib.Path(os.environ['APP_ROOT'])
phase = sys.argv[1]
with (p/'events').open('a') as f: f.write(phase+'\\n')
if phase == 'start':
    with (p/'restarts').open('a') as f: f.write('start\\n')
    if os.environ.get('FAKE_MUTATE') == '1':
        (p/'shared/data/sessions/value').write_text('mutated')
''')
        self.command("ps", """import json, os, pathlib, sys
root=pathlib.Path(os.environ['APP_ROOT'])
registry=root/'processes.json'
rows=json.loads(registry.read_text()) if registry.exists() else {}
if '-axo' in sys.argv:
    for pid, cwd in rows.items():
        if (root/('alive-'+pid)).exists(): print(pid+' Python')
else:
    pid=sys.argv[sys.argv.index('-p')+1]
    if (root/('alive-'+pid)).exists(): print('Fri Oct 2 00:00:00 2026 S')
""")
        self.command("pgrep", "import sys; sys.exit(1)\n")
        self.command("lsof", """import json, os, pathlib, sys
root=pathlib.Path(os.environ['APP_ROOT'])
registry=root/'processes.json'
rows=json.loads(registry.read_text()) if registry.exists() else {}
if '-p' in sys.argv:
    pid=sys.argv[sys.argv.index('-p')+1]
    if pid in rows: print('n'+rows[pid])
""")
        self.command("npm", "import sys\nsys.exit(0)\n")
        for name in ("node", "codex", "launchctl"):
            self.command(name, "import sys\nsys.exit(0)\n")
        self.command("pip-fake", '''import os, pathlib, sys
p=pathlib.Path(os.environ['APP_ROOT'])
with (p/'pip-calls').open('a') as f: f.write(' '.join(sys.argv[1:])+'\\n')
sys.exit(int(os.environ.get('FAKE_PIP_FAIL','0')))
''')
        self.env.update(DCX_BUILD_CMD=str(self.bin / "build"), DCX_RESTART_CMD=str(self.bin / "restart"), DCX_PIP_CMD=str(self.bin / "pip-fake"))
        src = root / "src"
        src.mkdir()
        self.git("init", "-b", "main", str(src))
        self.git("-C", str(src), "config", "user.email", "test@example.invalid")
        self.git("-C", str(src), "config", "user.name", "Test")
        (src / "backend").mkdir()
        (src / "frontend").mkdir()
        (src / "frontend/.keep").touch()
        (src / "backend/requirements.txt").write_text("example==1\n")
        (src / "backend/constraints.txt").write_text("example==1\n")
        self.src = src
        self.a = self.commit("A")
        (src / "version").write_text("B")
        self.b = self.commit("B")
        bare = root / "remote.git"
        self.git("clone", "--bare", str(src), str(bare))
        self.git("clone", str(bare), str(self.root / "repo"))
        self.env["DCX_REPO_URL"] = str(bare)
        for folder in ("shared/data/sessions", "shared/data/work", "shared/snapshots", "shared/venvs", "logs", "releases"):
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        (self.root / "shared/data/sessions/value").write_text("original")
        (self.root / "shared/data/work/runs.sqlite").write_text("work-before")
        (self.root / "shared/app.env").write_text("OPENAI_API_KEY=sk-test\n")
        (self.root / "shared/runtime.env").write_text("NEXT_PUBLIC_API_URL=http://127.0.0.1:18400\n")
        self.set_current(self.a)
        (self.root / "shared/deploy-history").write_text(f"{self.a} -\n")
        self.ci()

    def command(self, name, body):
        p = self.bin / name
        p.write_text(f"#!{sys.executable}\n" + body)
        p.chmod(0o755)

    def git(self, *args):
        return subprocess.check_output([shutil.which("git"), *args], stderr=subprocess.DEVNULL, text=True).strip()

    def commit(self, message):
        self.git("-C", str(self.src), "add", ".")
        self.git("-C", str(self.src), "commit", "-m", message)
        return self.git("-C", str(self.src), "rev-parse", "HEAD")

    def ci(self, status="completed", conclusion="success", attempt=1):
        self.env["FAKE_CI"] = json.dumps({"workflow_runs": [{"head_sha": self.b, "head_branch": "main", "event": "push", "status": status, "conclusion": conclusion, "id": 123, "run_attempt": attempt}]})

    def set_current(self, sha):
        (self.root / f"releases/{sha}/backend").mkdir(parents=True, exist_ok=True)
        (self.root / "current").unlink(missing_ok=True)
        (self.root / "current").symlink_to(f"releases/{sha}")

    @property
    def current(self):
        p = self.root / "current"
        return p.resolve().name if p.is_symlink() else ""

    @property
    def logs(self):
        p = self.root / "logs/deploy.log"
        return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []

    def run_deploy(self, **env):
        r = subprocess.run([self.env["DCX_BASH"], str(SCRIPTS / "deploy.sh")], env=dict(self.env, **env), capture_output=True, text=True, timeout=45)
        self.output = r.stdout + r.stderr
        return r.returncode, self.logs[-1] if self.logs else None

    def lib(self, command, **env):
        r = subprocess.run([self.env["DCX_BASH"], "-c", 'set -euo pipefail; . "$1/env.sh"; . "$1/lib.sh"; ' + command, "test", str(SCRIPTS)], env=dict(self.env, **env), capture_output=True, text=True, timeout=45)
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()


@pytest.fixture
def macmini(tmp_path):
    return Macmini(tmp_path)


@pytest.fixture
def owned_listener(macmini):
    """Simulated listener inventory: sandbox forbids bind; signal a real child."""
    import time
    m = macmini
    program = '''import os,pathlib,signal,sys,time
root=pathlib.Path(sys.argv[1]); alive=root/('alive-'+str(os.getpid()))
def stop(*_):
    alive.unlink(missing_ok=True); sys.exit(0)
signal.signal(signal.SIGTERM,stop)
alive.touch(); (root/'listener-port').write_text('18499')
time.sleep(120)
'''
    p = subprocess.Popen([sys.executable, '-c', program, str(m.root)], cwd=m.root)
    try:
        for _ in range(200):
            if (m.root/'listener-port').exists() or p.poll() is not None:
                break
            time.sleep(.01)
        assert p.poll() is None, 'test listener failed to start'
        port = (m.root/'listener-port').read_text()
        (m.root/'processes.json').write_text(json.dumps({str(p.pid): str(m.root)}))
        m.command('lsof', f'''import pathlib,sys
root=pathlib.Path({str(m.root)!r})
if '-iTCP:{port}' in sys.argv and (root/'alive-{p.pid}').exists(): print({p.pid})
''')
        yield p, port
    finally:
        if p.poll() is None:
            p.terminate()
        p.wait(timeout=5)
