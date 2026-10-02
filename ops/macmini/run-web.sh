#!/bin/bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/env.sh"
. "$HERE/lib.sh"
# KeepAlive retries without starting a writer during snapshot/restore.
if [[ -e "$MAINTENANCE" ]]; then
    sleep 10
    exit 0
fi
sha="$(current_sha)"
[[ -n "$sha" ]] || { echo 'current 릴리스가 없습니다' >&2; exit 1; }
[[ $# == 0 || "${1:-}" == --print-cmd ]] || exit 2
exec python3.12 - "$APP_ROOT" "$sha" "$DCX_WEB_PORT" "${1:-}" <<'PY'
import os, pathlib, re, shlex, sys
root=pathlib.Path(sys.argv[1]); sha=sys.argv[2]; port=sys.argv[3]
env={k:os.environ[k] for k in ('HOME','PATH','TMPDIR') if k in os.environ}
p=root/'shared/runtime.env'
for line in p.read_text().splitlines() if p.exists() else []:
    match=re.match(r'^\s*(?:export\s+)?(NEXT_PUBLIC_[A-Za-z0-9_]+)\s*=\s*(.*?)\s*$',line)
    if match: env[match[1]]=' '.join(shlex.split(match[2],comments=True))
env['PORT']=port
args=['node_modules/.bin/next','start','-H','127.0.0.1','-p',port]
if sys.argv[4]=='--print-cmd':
    print(' '.join(shlex.quote(k+'='+v) for k,v in sorted(env.items()) if k.startswith('NEXT_PUBLIC_') or k=='PORT')+' '+' '.join(args))
else:
    os.chdir(root/'releases'/sha/'frontend')
    (root/'shared/web.pid').write_text(str(os.getpid())+'\n')
    os.execve(args[0],args,env)
PY
