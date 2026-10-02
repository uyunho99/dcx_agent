#!/bin/bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/env.sh"
. "$HERE/lib.sh"
sha="$(current_sha)"
[[ -n "$sha" ]] || { echo 'current 릴리스가 없습니다' >&2; exit 1; }
if [[ "${1:-}" == --print-cmd ]]; then
    printf 'DCX_RELEASE_SHA=%s .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port %s\n' "$sha" "$DCX_API_PORT"
    exit 0
fi
[[ $# == 0 ]] || exit 2
if [[ "$DCX_LAUNCH_LABEL" == ai.person-a.dcx-agent-qa ]]; then codex --version; fi
# dotenv parser: never evaluate configuration as shell code or print secrets.
exec python3.12 - "$APP_ROOT" "$sha" "$DCX_API_PORT" <<'PY'
import os, pathlib, sys
root=pathlib.Path(sys.argv[1]); sha=sys.argv[2]; port=sys.argv[3]
backend=root/'releases'/sha/'backend'
# Use the release interpreter's python-dotenv, also used by the application.
program='''import os,pathlib,sys
from dotenv import dotenv_values
root=pathlib.Path(sys.argv[1]); sha=sys.argv[2]; port=sys.argv[3]
for name in ('app.env','runtime.env'):
    os.environ.update({k:v for k,v in dotenv_values(root/'shared'/name, interpolate=False).items() if v is not None})
os.environ['DCX_RELEASE_SHA']=sha
os.chdir(root/'releases'/sha/'backend')
(root/'shared/api.pid').write_text(str(os.getpid())+'\\n')
os.execv('.venv/bin/uvicorn',['.venv/bin/uvicorn','app.main:app','--host','127.0.0.1','--port',port])
'''
os.execv(str(backend/'.venv/bin/python'), [str(backend/'.venv/bin/python'), '-c', program, str(root), sha, port])
PY
