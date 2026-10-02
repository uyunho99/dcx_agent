#!/bin/bash
# Render only: install.sh --dry-run --output-dir /tmp/dcx-plan [--qa]
# Production: sudo APP_ROOT=/path/to/dcx-agent ./install.sh (interactive y).
set -Eeuo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
dry=false
qa=false
output=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) dry=true ;;
        --qa) qa=true ;;
        --output-dir) [[ $# -ge 2 && -n "$2" ]] || exit 2; output="$2"; shift ;;
        *) echo '사용법: install.sh [--qa] [--dry-run --output-dir DIR]' >&2; exit 2 ;;
    esac
    shift
done
if $dry && [[ -z "$output" ]]; then echo '--dry-run에는 --output-dir이 필요합니다' >&2; exit 2; fi
TARGET_USER="${SUDO_USER:-$(id -un)}"
TARGET_HOME="$HOME"
if [[ -n "${SUDO_USER:-}" ]]; then
    TARGET_HOME="$(/usr/bin/dscl . -read "/Users/$TARGET_USER" NFSHomeDirectory | awk '{print $2}')"
fi
export HOME="$TARGET_HOME"
if $qa; then
    export APP_ROOT="${APP_ROOT:-$HOME/srv/dcx-agent-qa}"
    export DCX_API_PORT="${DCX_API_PORT:-8401}" DCX_WEB_PORT="${DCX_WEB_PORT:-3401}"
fi
. "$HERE/env.sh"
. "$HERE/lib.sh"
if $qa; then
    export DCX_LAUNCH_LABEL=ai.person-a.dcx-agent-qa INSTALL_DOMAIN="gui/$(id -u)"
    destination="$HOME/Library/LaunchAgents"
else
    export DCX_LAUNCH_LABEL=ai.person-a.dcx-agent INSTALL_DOMAIN=system
    destination=/Library/LaunchDaemons
fi
# Explicit overrides are supported, but protected demo ports are never targets.
for port in "$DCX_API_PORT" "$DCX_WEB_PORT"; do
    case "$port" in
        ''|*[!0-9]*|3000|3310|3311|8310|8311) echo '사용할 수 없는 포트입니다' >&2; exit 2 ;;
    esac
    [[ "$port" -ge 1024 && "$port" -le 65535 ]] || exit 2
done
[[ "$DCX_API_PORT" != "$DCX_WEB_PORT" ]] || exit 2
printf '만들 경로: %s/{repo,releases,shared/data,shared/venvs,shared/snapshots,ops,logs}\n' "$APP_ROOT"
printf '등록 위치: %s\n' "$destination"
for job in deploy api web; do printf '잡: %s.%s\n' "$DCX_LAUNCH_LABEL" "$job"; done
printf '내릴 포트: %s %s (api/web pid 자손 및 릴리스 Python 작업자 포함)\n' "$DCX_WEB_PORT" "$DCX_API_PORT"
printf '%s\n' '건드리지 않음: 3000 3310 3311 8310 8311' 'main 머리 커밋을 정식 빌드해 첫 릴리스로 · 손 clone은 설치 후 삭제'
printf 'runtime.env: AUTHOR_SALT_PATH=%s/shared/data/.author_salt\n' "$APP_ROOT"
if ! $dry; then
    printf '진행하려면 y 입력: '
    answer=""
    read -r answer || true
    [[ "$answer" == y ]] || exit 0
    [[ -t 0 ]] || { echo '실제 설치는 대화형 터미널에서 y 확인이 필요합니다' >&2; exit 1; }
    [[ "$(uname -s)" == Darwin ]] || { echo '실제 설치는 macOS 전용입니다' >&2; exit 1; }
    if $qa; then
        [[ $EUID -ne 0 ]] || { echo 'QA는 sudo 없이 실행하세요' >&2; exit 1; }
    else
        [[ $EUID == 0 && -n "${SUDO_USER:-}" ]] || { echo '운영 설치는 sudo로 실행하세요' >&2; exit 1; }
    fi
    preflight
else
    # No log writes or service commands during rendering.
    for binary in node npm python3.12 codex git curl; do
        command -v "$binary" >/dev/null || { echo "실행 파일 없음: $binary" >&2; exit 1; }
    done
fi
as_user() {
    if [[ $EUID == 0 ]] && ! $qa; then
        sudo -u "$TARGET_USER" env HOME="$TARGET_HOME" APP_ROOT="$APP_ROOT" PATH="$PATH" \
            DCX_API_PORT="$DCX_API_PORT" DCX_WEB_PORT="$DCX_WEB_PORT" DCX_REPO_URL="$DCX_REPO_URL" "$@"
    else
        "$@"
    fi
}
# Keep logs writable by the daemon user even during a sudo installation.
log() {
    as_user /bin/bash -c '. "$1/env.sh"; . "$1/lib.sh"; sha="$2"; log "$3" "$4"' \
        dcx-install "$HERE" "${sha:-}" "$1" "${2:-}"
}
# Render templates structurally: XML metacharacters and spaces stay valid.
render() {
    python3.12 - "$HERE" "$1" "$APP_ROOT" "$TARGET_USER" "$TARGET_HOME" "$DCX_LAUNCH_LABEL" "$INSTALL_DOMAIN" "$DCX_API_PORT" "$DCX_WEB_PORT" "$qa" <<'PY'
import pathlib, plistlib, shlex, sys
here,out,root,user,home,label,domain,api,web,qa=sys.argv[1:]
out=pathlib.Path(out); out.mkdir(parents=True,exist_ok=True)
values={'__APP_ROOT__':root,'__USER__':user,'__HOME__':home,'__LABEL__':label,'__DOMAIN__':domain,'__API_PORT__':api,'__WEB_PORT__':web}
def fill(x):
    if isinstance(x,str):
        for k,v in values.items(): x=x.replace(k,v)
        return x
    if isinstance(x,list): return [fill(v) for v in x]
    if isinstance(x,dict): return {k:fill(v) for k,v in x.items()}
    return x
for job in ('deploy','api','web'):
    p=pathlib.Path(here)/'launchd'/('ai.person-a.dcx-agent.'+job+'.plist')
    data=fill(plistlib.loads(p.read_bytes()))
    if qa=='true': data.pop('UserName')
    (out/(label+'.'+job+'.plist')).write_bytes(plistlib.dumps(data,sort_keys=False))
config={'AUTHOR_SALT_PATH':root+'/shared/data/.author_salt','STORAGE':'local','LOCAL_DATA_DIR':root+'/shared/data',
        'LABEL_GPT_BACKEND':'codex_exec','JEV_BACKEND':'fake','CORS_ORIGINS':'http://localhost:'+web,'NEXT_PUBLIC_API_URL':'http://localhost:'+api}
(out/'runtime.env').write_text(''.join(k+'='+shlex.quote(v)+'\n' for k,v in config.items()))
(out/'launch.env').write_text(''.join('export '+k+'='+shlex.quote(v)+'\n' for k,v in {
    'DCX_LAUNCH_LABEL':label,'DCX_API_PORT':api,'DCX_WEB_PORT':web,
    'DCX_HEALTH_API':'http://127.0.0.1:'+api+'/health','DCX_HEALTH_WEB':'http://127.0.0.1:'+web+'/pipeline/start'}.items()))
PY
}
if $dry; then render "$output"; echo "렌더 완료: $output"; exit 0; fi

# Real operations below this boundary are deliberately unreachable in tests.
as_user mkdir -p "$SHARED/data" "$SHARED/venvs" "$SHARED/snapshots" "$APP_ROOT/releases" "$APP_ROOT/logs" "$APP_ROOT/ops"
acquire_lock || { echo '배포가 진행 중입니다' >&2; exit 1; }
trap 'log error "\"line\":$LINENO"' ERR
[[ ! -s "$SHARED/deploy-state" ]] || { echo '진행 중인 배포 복구부터 완료하세요' >&2; exit 1; }
# Secrets/data are supplied by the operator; never guess another application's source.
[[ -f "$SHARED/app.env" && -f "$SHARED/data/.author_salt" ]] || {
    echo 'shared/app.env 및 기존 작성자 salt를 shared/data/.author_salt에 준비하세요' >&2; exit 1;
}
as_user chmod 600 "$SHARED/app.env" "$SHARED/data/.author_salt"
staging="$(as_user mktemp -d "$APP_ROOT/.install.XXXXXX")"
render "$staging"
if [[ $EUID == 0 ]]; then chown -R "$TARGET_USER" "$staging"; fi
as_user cp "$staging/runtime.env" "$SHARED/runtime.env"
as_user cp "$staging/launch.env" "$SHARED/launch.env"
if [[ "$HERE" != "$APP_ROOT/ops" ]]; then as_user cp -R "$HERE/." "$APP_ROOT/ops/"; fi
first=false
sha="$(current_sha)"
if [[ -z "$sha" ]]; then
    first=true
    if [[ ! -d "$APP_ROOT/repo/.git" ]]; then as_user git clone --quiet "$DCX_REPO_URL" "$APP_ROOT/repo"; fi
    as_user git -C "$APP_ROOT/repo" fetch --quiet origin main
    sha="$(as_user git -C "$APP_ROOT/repo" rev-parse --verify 'origin/main^{commit}')"
    as_user /bin/bash -c '. "$1/env.sh"; . "$1/lib.sh"; build_release "$2"' dcx-install "$APP_ROOT/ops" "$sha"
    # Prepare the fetch clone without moving the running manual tree or its venv.
    as_user git clone --quiet "$DCX_REPO_URL" "$staging/repo"
fi
# Hold KeepAlive launches before terminating writers and taking the snapshot.
restart_services stop
if $first; then
    snapshot="$(as_user /bin/bash -c '. "$1/env.sh"; . "$1/lib.sh"; snapshot_sessions "$2"' dcx-install "$APP_ROOT/ops" "$sha")"
    as_user /bin/bash -c '. "$1/env.sh"; . "$1/lib.sh"; switch_to "$2"' dcx-install "$APP_ROOT/ops" "$sha"
    printf '%s %s\n' "$sha" "$snapshot" > "$HISTORY"
    if [[ $EUID == 0 ]]; then chown "$TARGET_USER" "$HISTORY"; fi
fi
mkdir -p "$destination"
for job in api web deploy; do
    label="$DCX_LAUNCH_LABEL.$job"
    dest="$destination/$label.plist"
    cp "$staging/$label.plist" "$dest"
    if ! $qa; then chown root:wheel "$dest"; fi
    chmod 644 "$dest"
    plutil -lint "$dest"
    if launchctl print "$INSTALL_DOMAIN/$label" >/dev/null 2>&1; then
        launchctl bootout "$INSTALL_DOMAIN/$label"
        for ((attempt=0; attempt<30; attempt++)); do
            launchctl print "$INSTALL_DOMAIN/$label" >/dev/null 2>&1 || break
            sleep 1
        done
    fi
    launchctl enable "$INSTALL_DOMAIN/$label"
    launchctl bootstrap "$INSTALL_DOMAIN" "$dest"
done
restart_services start
if ! wait_healthy "$DCX_HEALTH_TIMEOUT" "$sha"; then
    log unhealthy '"reason":"installation health check failed; manual clone retained"'
    echo '설치 상태 확인 실패: 손 clone과 스냅샷을 보존했습니다' >&2
    exit 1
fi
if $first; then
    # Never delete the manual clone until the formally built release is healthy.
    as_user mv "$APP_ROOT/repo" "$staging/manual-clone"
    as_user mv "$staging/repo" "$APP_ROOT/repo"
fi
as_user rm -rf "$staging"
log deployed '"installation":true'
if [[ $EUID == 0 ]]; then chown "$TARGET_USER" "$APP_ROOT/logs/deploy.log"; fi
printf '설치 완료: %s/ops/dcxctl status\n' "$APP_ROOT"
