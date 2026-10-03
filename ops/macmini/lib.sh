#!/bin/bash
# Shared by deploy.sh and dcxctl. Requires env.sh; compatible with Bash 3.2.

utc_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
epoch_now() { date +%s; }
sha256() {
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 | awk '{print $1}'
    else
        sha256sum | awk '{print $1}'
    fi
}
atomic_move() {
    if [[ "$(uname -s)" == Darwin ]]; then
        mv -fh "$1" "$2"
    else
        mv -fT "$1" "$2"
    fi
}
log() { # decision [JSON object or comma-separated JSON fields]
    mkdir -p "$APP_ROOT/logs"
    if command -v python3.12 >/dev/null 2>&1; then
        python3.12 - "$APP_ROOT/logs/deploy.log" "$(utc_now)" "${sha:-}" "$1" "${2:-}" <<'PY'
import json, sys
path, at, sha, decision, extra = sys.argv[1:]
record = dict(at=at, sha=sha, decision=decision)
if extra:
    record.update(json.loads(extra if extra.startswith('{') else '{'+extra+'}'))
with open(path, 'a') as f:
    f.write(json.dumps(record, separators=(',', ':'))+'\n')
PY
    else
        # Preflight must also report a missing Python interpreter.
        printf '{"at":"%s","sha":"","decision":"error","missing":"python3.12"}\n' "$(utc_now)" >> "$APP_ROOT/logs/deploy.log"
    fi
}
preflight() {
    local binary
    for binary in node npm python3.12 codex git curl; do
        if ! command -v "$binary" >/dev/null 2>&1; then
            log error "\"missing\":\"$binary\""
            return 1
        fi
    done
}
current_sha() {
    [[ -L "$APP_ROOT/current" ]] || return 0
    basename "$(readlink "$APP_ROOT/current")"
}
release() {
    local lock="$SHARED/deploy.lock"
    if [[ "$(cat "$lock/pid" 2>/dev/null || true)" == "$$" ]]; then
        rm -rf "$lock"
    fi
}
acquire_lock() {
    local lock="$SHARED/deploy.lock"
    mkdir -p "$SHARED"
    if ! mkdir "$lock" 2>/dev/null; then
        # An advisory flock serializes stale-owner takeover, including the
        # mkdir-to-pid publication window. Kernel releases it after a crash.
        python3.12 - "$lock" "$$" <<'PY'
import fcntl, os, pathlib, shutil, sys, time
lock = pathlib.Path(sys.argv[1]); pid = sys.argv[2]
with open(str(lock)+'.guard', 'a') as guard:
    fcntl.flock(guard, fcntl.LOCK_EX)
    if lock.exists():
        try:
            owner = int((lock/'pid').read_text())
        except (OSError, ValueError):
            # A live creator may not have published its pid yet.
            if time.time() - lock.stat().st_mtime < 5:
                sys.exit(1)
            owner = None
        if owner and owner > 0:
            try:
                os.kill(owner, 0)
            except ProcessLookupError:
                pass
            except PermissionError:
                sys.exit(1)
            else:
                sys.exit(1)
        shutil.rmtree(lock)
    lock.mkdir()
    (lock/'pid').write_text(pid+'\n')
PY
        [[ $? == 0 ]] || return 1
    else
        echo $$ > "$lock/pid"
    fi
    trap release EXIT
}
switch_to() {
    [[ "$1" != */* && -n "$1" && -d "$APP_ROOT/releases/$1" ]] || return 1
    # Remove a dangling temporary link left by an interrupted rename.
    rm -f "$APP_ROOT/current.tmp"
    ln -s "releases/$1" "$APP_ROOT/current.tmp" || return 1
    atomic_move "$APP_ROOT/current.tmp" "$APP_ROOT/current"
}

# Build subprocesses receive only explicit public configuration. Never source
# app.env, runtime.env, or inherit arbitrary caller secrets in a build process.
clean_build() { # shell program [positional arguments]
    python3.12 - "$SHARED/runtime.env" "$@" <<'PY'
import os, re, shlex, sys
runtime, program = sys.argv[1:3]
env = {k: os.environ[k] for k in ('PATH', 'HOME', 'APP_ROOT', 'TMPDIR', 'DCX_PIP_CMD') if k in os.environ}
# Fakes are available only when the caller explicitly requests a test hook.
if os.environ.get('DCX_BUILD_CMD') or os.environ.get('DCX_PIP_CMD'):
    env.update((k,v) for k,v in os.environ.items() if k.startswith('FAKE_'))
try:
    lines = open(runtime).readlines()
except FileNotFoundError:
    lines = []
for line in lines:
    match = re.match(r'^\s*(?:export\s+)?(NEXT_PUBLIC_[A-Za-z0-9_]+)\s*=\s*(.*?)\s*$', line)
    if match:
        parts = shlex.split(match[2], comments=True)
        env[match[1]] = ' '.join(parts)
env.setdefault('NEXT_PUBLIC_API_URL', 'http://127.0.0.1:'+os.environ['DCX_API_PORT'])
os.execve('/bin/bash', ['/bin/bash', '-c', program, 'dcx-build']+sys.argv[3:], env)
PY
}
build_config_hash() {
    clean_build 'python3.12 -c '\''import json,os; print(json.dumps({k:v for k,v in os.environ.items() if k.startswith("NEXT_PUBLIC_")},sort_keys=True))'\''' | sha256
}
build_release() { # sha
    local target="$1" release_dir="$APP_ROOT/releases/$1" config key venv
    config="$(build_config_hash)" || return 1
    if [[ -f "$release_dir/.built" && "$(cat "$release_dir/.build-config" 2>/dev/null)" == "$config" ]]; then
        return 0
    fi
    # Rebuilding a current release in place would modify live code.
    if [[ "$(current_sha)" == "$target" ]]; then
        log error '"reason":"cannot rebuild active release; deploy another commit first"'
        return 1
    fi
    rm -rf "$release_dir"
    mkdir -p "$release_dir" "$SHARED/venvs" || return 1
    if ! (set -o pipefail; git -C "$APP_ROOT/repo" archive "$target" | tar -x -C "$release_dir"); then
        rm -rf "$release_dir"
        return 1
    fi
    if [[ -n "${DCX_BUILD_CMD:-}" ]]; then
        if ! clean_build 'cd "$2" && "$3" "$1"' "$target" "$release_dir" "$DCX_BUILD_CMD"; then
            rm -rf "$release_dir"
            return 1
        fi
    else
        # Constraints and interpreter version are part of the cache identity.
        key="$(set -o pipefail; (
            cat "$release_dir/backend/requirements.txt" &&
            if [[ -f "$release_dir/backend/constraints.txt" ]]; then
                cat "$release_dir/backend/constraints.txt" && python3.12 --version
            else
                python3.12 --version && printf '%s\n' 'no-constraints'
            fi
        ) | sha256)" || { rm -rf "$release_dir"; return 1; }
        venv="$SHARED/venvs/$key"
        if [[ ! -f "$venv/.complete" ]]; then
            rm -rf "$venv"
            if ! clean_build '
                python3.12 -m venv "$1" || exit 1
                pip="${DCX_PIP_CMD:-$1/bin/pip}"
                requirements="$2/backend/requirements.txt"
                constraints="$2/backend/constraints.txt"
                if [[ -f "$constraints" ]]; then
                    "$pip" install -r "$requirements" -c "$constraints"
                else
                    "$pip" install -r "$requirements"
                fi
            ' "$venv" "$release_dir"; then
                rm -rf "$venv" "$release_dir"
                return 1
            fi
            touch "$venv/.complete"
        fi
        ln -s "$venv" "$release_dir/backend/.venv" || return 1
        if ! clean_build 'cd "$1/frontend" && npm ci && npm run build' "$release_dir"; then
            rm -rf "$release_dir"
            return 1
        fi
    fi
    # Link secrets only after npm/lifecycle scripts have finished.
    ln -sf "$SHARED/app.env" "$release_dir/.env" || return 1
    printf '%s\n' "$config" > "$release_dir/.build-config"
    touch "$release_dir/.built"
}
snapshot_sessions() { # sha; stdout is exclusively the snapshot path
    python3.12 - "$SHARED" "$1" <<'PY'
from datetime import datetime, timezone
import pathlib, re, shutil, sys
shared = pathlib.Path(sys.argv[1]); base = shared/'snapshots'
base.mkdir(parents=True, exist_ok=True)
snap = base/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+sys.argv[2])
snap.mkdir()
for name in ('sessions','work'):
    source = shared/'data'/name
    if source.exists():
        shutil.copytree(source, snap/name, symlinks=True, copy_function=shutil.copy2)
# Failed-data backups are evidence, not successful snapshots; retain them.
complete = sorted(p for p in base.iterdir() if p.is_dir() and not re.search(r'-failed(?:-\d+)?$', p.name))
for old in complete[:-5]:
    shutil.rmtree(old)
print(snap)
PY
}
restore_sessions() { # snapshot directory; services and workers MUST be stopped
    python3.12 - "$SHARED" "$1" <<'PY'
import pathlib, shutil, sys
shared = pathlib.Path(sys.argv[1]); snap = pathlib.Path(sys.argv[2])
if not snap.is_dir() or snap.parent.resolve() != (shared/'snapshots').resolve():
    raise ValueError('missing or invalid snapshot')
index = 0
while True:
    backup = snap.with_name(snap.name+'-failed'+('-'+str(index) if index else ''))
    try:
        backup.mkdir()
        break
    except FileExistsError:
        index += 1
(shared/'data').mkdir(exist_ok=True)
for name in ('sessions','work'):
    live = shared/'data'/name
    if live.exists() or live.is_symlink():
        # Every replay preserves the current tree, including partial restores.
        live.rename(backup/name)
    if (snap/name).exists():
        shutil.copytree(snap/name, live, symlinks=True, copy_function=shutil.copy2)
PY
}

# Identify Python workers and Node web processes by executable and physical cwd.
# Never infer ownership merely from a command containing a release path.
worker_pids() {
    python3.12 - "$APP_ROOT" <<'PY'
import os, pathlib, shutil, subprocess, sys
root = pathlib.Path(sys.argv[1]).resolve()
rows = subprocess.check_output(['ps','-axo','pid=,comm='], text=True).splitlines()
for row in rows:
    fields = row.strip().split(None, 1)
    if len(fields) != 2:
        continue
    command = os.path.basename(fields[1]).lower()
    python = 'python' in command
    node = command in ('node', 'nodejs')
    if not (python or node):
        continue
    pid = int(fields[0])
    if pid == os.getpid():
        continue
    try:
        if sys.platform.startswith('linux'):
            cwd = pathlib.Path(os.readlink('/proc/%s/cwd' % pid)).resolve()
        else:
            data = subprocess.check_output([shutil.which('lsof') or '/usr/sbin/lsof','-a','-p',str(pid),'-d','cwd','-Fn'], stderr=subprocess.DEVNULL, text=True)
            cwd = pathlib.Path(next(line[1:] for line in data.splitlines() if line.startswith('n'))).resolve()
        allowed = [root] if node else [root/'releases', root/'repo']
        if not any(cwd == path or path in cwd.parents for path in allowed):
            continue
    except (OSError, ValueError, StopIteration, subprocess.CalledProcessError):
        continue
    print(pid)
PY
}
descendants() {
    local child
    for child in $(pgrep -P "$1" 2>/dev/null || true); do
        descendants "$child"
        echo "$child"
    done
}
terminate_pids() { # fixed PID set, never rediscover after TERM
    validate_service_ports || return 1
    python3.12 - "$@" <<'PY'
import os, signal, subprocess, sys, time
pids = set(int(p) for arg in sys.argv[1:] for p in arg.split() if p.isdigit() and int(p)>1)
pids.discard(os.getpid()); pids.discard(os.getppid())
def identity(pid):
    try:
        value = subprocess.check_output(['ps','-p',str(pid),'-o','lstart=,stat='], stderr=subprocess.DEVNULL, text=True).strip()
        return None if not value or value.split()[-1].startswith('Z') else value.rsplit(None, 1)[0]
    except subprocess.CalledProcessError:
        return None
original = {p: identity(p) for p in pids}
for p in pids:
    if original[p]:
        try: os.kill(p, signal.SIGTERM)
        except ProcessLookupError: pass
deadline = time.monotonic()+20
while time.monotonic() < deadline:
    pids = {p for p in pids if original[p] and identity(p)==original[p]}
    if not pids: break
    time.sleep(.1)
for p in pids:
    if identity(p)==original[p]:
        try: os.kill(p, signal.SIGKILL)
        except ProcessLookupError: pass
# SIGKILL is asynchronous: wait for writers to exit before copying SQLite.
deadline = time.monotonic()+5
while pids and time.monotonic() < deadline:
    pids = {p for p in pids if identity(p)==original[p]}
    if pids: time.sleep(.1)
if pids:
    raise RuntimeError('workers did not exit after SIGKILL')
PY
}
validate_service_ports() {
    local port
    for port in "$DCX_API_PORT" "$DCX_WEB_PORT"; do
        case "$port" in
            3000|3310|3311|8310|8311) ;;
            3400|8400) [[ "${APP_ROOT%/}" != "$HOME/srv/dcx-agent" ]] || continue ;;
            *) continue ;;
        esac
        log error "\"reason\":\"protected service port\",\"port\":\"$port\""
        return 1
    done
}
create_hold() {
    printf '%s %s\n' "$$" "${DCX_HOLD_REASON:-service-stop}" > "$MAINTENANCE.tmp" || return 1
    mv -f "$MAINTENANCE.tmp" "$MAINTENANCE"
}
remove_own_hold() {
    local owner reason
    if [[ -f "$MAINTENANCE" ]]; then
        IFS=' ' read -r owner reason < "$MAINTENANCE" || true
        if [[ "$owner" == "$$" ]]; then rm -f "$MAINTENANCE"; fi
    fi
}
clear_stale_hold() {
    [[ ! -e "$SHARED/deploy-state" && -e "$MAINTENANCE" ]] || return 0
    [[ "${DEPLOY_DRY_RUN:-0}" != 1 ]] || return 0
    if python3.12 - "$MAINTENANCE" <<'PY_HOLD'
import os, pathlib, sys
p = pathlib.Path(sys.argv[1])
try:
    pid = int(p.read_text().split()[0])
    if pid <= 0: raise ValueError()
except (ValueError, IndexError):
    pid = None
if pid:
    try: os.kill(pid, 0)
    except ProcessLookupError: pass
    except PermissionError: sys.exit(1)
    else: sys.exit(1)
p.unlink()
PY_HOLD
    then
        log hold-cleared '"reason":"maintenance owner gone; no deploy-state"'
    fi
}
listener_pids() {
    validate_service_ports || return 1
    local port result status
    for port in "$DCX_API_PORT" "$DCX_WEB_PORT"; do
        status=0
        result="$("${DCX_LSOF:-$(command -v lsof || echo /usr/sbin/lsof)}" -nP -t -iTCP:"$port" -sTCP:LISTEN)" || status=$?
        # lsof returns 1 when no file matches; execution errors must fail closed.
        [[ $status -le 1 ]] || return 1
        [[ -z "$result" ]] || printf '%s\n' "$result"
    done
}
assert_services_stopped() {
    local listeners workers
    listeners="$(listener_pids)" || return 1
    workers="$(worker_pids)" || return 1
    if [[ -n "$listeners" || -n "$workers" ]]; then
        log error '"reason":"service listeners or workers remain; maintenance hold retained"'
        return 1
    fi
}
stop_services() {
    local service pid pids="" listeners
    validate_service_ports || return 1
    create_hold || return 1
    if [[ -n "${DCX_RESTART_CMD:-}" ]]; then
        "$DCX_RESTART_CMD" stop || return 1
    fi
    for service in api web; do
        pid="$(cat "$SHARED/$service.pid" 2>/dev/null || true)"
        case "$pid" in ''|*[!0-9]*) continue ;; esac
        # PID files are trusted only while the process cwd is our release.
        if python3.12 - "$pid" "$APP_ROOT/releases" <<'PY'
import os, pathlib, shutil, subprocess, sys
try:
    if sys.platform.startswith('linux'):
        cwd=os.readlink('/proc/'+sys.argv[1]+'/cwd')
    else:
        out=subprocess.check_output([shutil.which('lsof') or '/usr/sbin/lsof','-a','-p',sys.argv[1],'-d','cwd','-Fn'],text=True,stderr=subprocess.DEVNULL)
        cwd=next(x[1:] for x in out.splitlines() if x.startswith('n'))
    pathlib.Path(cwd).resolve().relative_to(pathlib.Path(sys.argv[2]).resolve())
except (OSError,ValueError,StopIteration,subprocess.CalledProcessError): sys.exit(1)
PY
        then
            pids="$pids $(descendants "$pid") $pid"
        fi
    done
    listeners="$(listener_pids)" || return 1
    pids="$pids $listeners"
    # Stop parents before scanning for detached workers they could still spawn.
    terminate_pids "$pids" || return 1
    pids="$(worker_pids)" || return 1
    terminate_pids "$pids" || return 1
    assert_services_stopped || return 1
    # Catch a launch that passed the hold check just before we published it.
    sleep 1 || return 1
    assert_services_stopped
}
start_services() {
    rm -f "$MAINTENANCE" || return 1
    # Sleeping holders exit within 10 seconds; launchd KeepAlive retries them.
    if [[ -n "${DCX_RESTART_CMD:-}" ]]; then
        "$DCX_RESTART_CMD" start
    fi
}
restart_services() { # Optional stop/start phases; no argument performs both.
    case "${1:-restart}" in
        stop) stop_services ;;
        start) start_services ;;
        restart) stop_services && start_services ;;
        *) return 1 ;;
    esac
}
http_ok() { # timeout URL; redirects are not readiness.
    local code
    code="$(curl -fsS --max-time "$1" -o /dev/null -w '%{http_code}' "$2" 2>/dev/null)" || return 1
    [[ "$code" == 200 ]]
}
wait_healthy() { # seconds sha
    local deadline=$((SECONDS + $1)) target="$2" response first remaining
    [[ "${DCX_FORCE_UNHEALTHY_SHA:-}" != "$target" ]] || return 1
    first="$(head -n 1 "$HISTORY" 2>/dev/null | awk '{print $1}' || true)"
    while :; do
        remaining=$((deadline - SECONDS))
        ((remaining > 0)) || return 1
        response="$(curl -fsS --max-time "$remaining" "$DCX_HEALTH_API" 2>/dev/null)" || response=""
        if python3.12 - "$response" "$target" "$first" <<'PY'
import json, sys
try:
    data=json.loads(sys.argv[1])
    ok=isinstance(data,dict) and data.get('status')=='ok' and (data.get('release')==sys.argv[2] or ('release' not in data and sys.argv[2]==sys.argv[3]))
except (ValueError,TypeError): ok=False
sys.exit(0 if ok else 1)
PY
        then
            remaining=$((deadline - SECONDS)); ((remaining > 0)) || return 1
            if http_ok "$remaining" "${DCX_HEALTH_API%/health}/sessions"; then
                remaining=$((deadline - SECONDS)); ((remaining > 0)) || return 1
                if http_ok "$remaining" "$DCX_HEALTH_WEB"; then
                    return 0
                fi
            fi
        fi
        ((SECONDS < deadline)) || return 1
        sleep 1
    done
}
ci_status() {
    local response
    response="$(curl -fsS --max-time 20 "$DCX_CI_API?head_sha=$1&event=push&branch=main&per_page=1" 2>/dev/null)" || { echo unknown; return; }
    python3.12 - "$response" "$1" <<'PY'
import json, sys
try:
    data = json.loads(sys.argv[1]); runs = data['workflow_runs']
    if not isinstance(runs, list): raise ValueError()
    if not runs:
        print('pending'); sys.exit()
    run = runs[0]
    if run['head_sha']!=sys.argv[2] or run['event']!='push' or run['head_branch']!='main': raise ValueError()
    status = run['status']; conclusion = run['conclusion']
    if status == 'completed' and conclusion == 'success': print('success')
    elif status == 'completed' and conclusion in ('failure','timed_out','startup_failure','action_required'):
        print('failed:%d:%d' % (int(run['id']),int(run['run_attempt'])))
    elif status in ('queued','in_progress','waiting','pending','requested') or (status=='completed' and conclusion in ('cancelled','skipped','neutral','stale')): print('pending')
    else: print('unknown')
except (KeyError,ValueError,TypeError,IndexError): print('unknown')
PY
}
local_ci_status() { # sha; runs the CI suite on this Mac once per commit
    local sha="$1" result="$SHARED/local-ci/$1" tree="$APP_ROOT/ci/$1" log="$APP_ROOT/logs/local-ci-$1.log" key venv
    if [[ -f "$result" ]]; then cat "$result"; return; fi
    mkdir -p "$SHARED/local-ci" "$APP_ROOT/ci" "$SHARED/venvs" "$APP_ROOT/logs"
    rm -rf "$tree"; mkdir -p "$tree"
    if ! (set -o pipefail; git -C "$APP_ROOT/repo" archive "$sha" | tar -x -C "$tree"); then
        rm -rf "$tree"; echo unknown; return
    fi
    key="$(cat "$tree/backend/requirements.txt" "$tree/backend/requirements-dev.txt" "$tree/backend/constraints.txt" 2>/dev/null | { cat; python3.12 --version; } | shasum -a 256 | cut -c1-16)"
    venv="$SHARED/venvs/ci-$key"
    # Isolated environment: never inherit operator keys or production data paths.
    if env -i HOME="$HOME" PATH="$PATH" TMPDIR="${TMPDIR:-/tmp}" /bin/bash -c '
        set -e; tree="$1"; venv="$2"; cd "$tree"
        if [[ ! -f "$venv/.complete" ]]; then
            rm -rf "$venv"; python3.12 -m venv "$venv"
            c=(); [[ -f backend/constraints.txt ]] && c=(-c backend/constraints.txt)
            "$venv/bin/pip" install -q -r backend/requirements.txt -r backend/requirements-dev.txt "${c[@]}"
            touch "$venv/.complete"
        fi
        # One rerun of only the failed tests absorbs known timing-sensitive flakes.
        "$venv/bin/python" -m pytest backend/tests -q -n auto || "$venv/bin/python" -m pytest backend/tests -q --lf
        npm ci --prefix frontend --silent
        npm --prefix frontend run lint
        npm --prefix frontend test
        npm --prefix frontend run build
    ' local-ci "$tree" "$venv" > "$log" 2>&1; then
        echo success > "$result"
    else
        echo "failed:local" > "$result"
    fi
    rm -rf "$tree"
    cat "$result"
}
prune_releases() {
    local keep dir
    keep=" $(current_sha) $(tail -n 3 "$HISTORY" 2>/dev/null | awk '{print $1}' | tr '\n' ' ') "
    for dir in "$APP_ROOT/releases"/*; do
        [[ -d "$dir" ]] || continue
        [[ "$keep" == *" $(basename "$dir") "* ]] || rm -rf "$dir"
    done
}

write_state() { # phase; sha/previous/snapshot from the locked transaction
    printf '%s %s %s %s\n' "$1" "$sha" "${previous:--}" "${snapshot:--}" > "$SHARED/deploy-state.tmp" || return 1
    # Optional second line preserves manual intent across history finalization.
    printf '%s\n' "${rollback_mode:-automatic}" >> "$SHARED/deploy-state.tmp" || return 1
    mv -f "$SHARED/deploy-state.tmp" "$SHARED/deploy-state"
}
rollback_candidate() {
    if [[ -z "$previous" || ! -d "$APP_ROOT/releases/$previous" ]]; then
        printf '%s\n' "$sha" > "$FAILED"
        log unhealthy '"rolled_back_to":null'
        rm -f "$SHARED/deploy-state"
        return 1
    fi
    write_state rolling-back || return 1
    printf '%s\n' "$sha" > "$FAILED" || return 1
    restart_services stop || { log error '"reason":"rollback stop failed"'; return 1; }
    restore_sessions "$snapshot" || { log error '"reason":"snapshot restore failed"'; return 1; }
    switch_to "$previous" || { log error '"reason":"rollback switch failed"'; return 1; }
    if [[ "${rollback_mode:-automatic}" == manual ]]; then
        # Atomic and idempotent: a replay must never remove the previous row.
        python3.12 - "$HISTORY" "$sha" <<'HISTORY_PY'
import pathlib,sys
p=pathlib.Path(sys.argv[1]); rows=p.read_text().splitlines()
if rows and rows[-1].split(' ',1)[0] == sys.argv[2]:
    tmp=p.with_suffix('.tmp')
    tmp.write_text('\n'.join(rows[:-1])+'\n'); tmp.replace(p)
HISTORY_PY
        [[ $? == 0 ]] || return 1
    fi
    restart_services start || { log error '"reason":"rollback start failed"'; return 1; }
    if wait_healthy "$DCX_HEALTH_TIMEOUT" "$previous"; then
        if [[ "${rollback_mode:-automatic}" == manual ]]; then
            log rolled-back "\"rolled_back_to\":\"$previous\"" || return 1
            rm -f "$SHARED/deploy-state"
            return $?
        fi
        rm -rf "$APP_ROOT/releases/$sha"
        log unhealthy "$(python3.12 -c 'import json,sys; print(json.dumps(dict(rolled_back_to=sys.argv[1],snapshot=sys.argv[2])))' "$previous" "$snapshot")"
    else
        log unhealthy-both "\"rolled_back_to\":\"$previous\""
    fi
    rm -f "$SHARED/deploy-state"
    return 1
}
