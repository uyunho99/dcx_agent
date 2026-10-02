"""Atomic check/launch/register of detached workers."""
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Thread
import time
from typing import Literal
from uuid import uuid4

from app.work.status import ACTIVE, database_path, public, refresh, transaction


def start(sid: str, version: str, kind: str, args: dict) -> dict:
    payload = json.dumps(args, allow_nan=False)
    labeler = args.get('labeler')
    if labeler is not None and not isinstance(labeler, str):
        raise ValueError('labeler must be a string')
    child = None
    try:
        with transaction(sid) as db:
            refresh(db)
            row = db.execute('''SELECT * FROM runs WHERE version=? AND kind=?
                AND labeler IS ? AND state IN ('running','paused')
                ORDER BY started_at DESC LIMIT 1''', (version, kind, labeler)).fetchone()
            if row:
                return public(row)
            if kind in ('segment', 'evidence'):
                conflict = db.execute("SELECT kind FROM runs WHERE version=? AND kind IN ('segment','evidence') AND kind<>? AND state IN ('running','paused')", (version, kind)).fetchone()
                if conflict:
                    from app.context.store import StoreError
                    raise StoreError('6단계 또는 근거 탐색 작업이 진행 중입니다. 일시 정지된 근거 탐색도 취소한 뒤 6단계를 다시 실행하세요.', 409, 'locked')
            run_id, now = uuid4().hex, time.time()
            env = dict(os.environ, LOCAL_DATA_DIR=str(database_path(sid).parents[2]),
                       DCX_WORK_RUN_ID=run_id)
            command = [sys.executable, '-m', 'app.work.worker', kind, '--sid', sid,
                       '--version', version, '--args-json', payload]
            child = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[2],
                                     env=env, start_new_session=True,
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
            db.execute('''INSERT INTO runs
                (run_id,version,kind,labeler,args_json,pid,state,heartbeat_at,started_at)
                VALUES (?,?,?,?,?,?,'running',?,?)''',
                       (run_id, version, kind, labeler, payload, child.pid, now, now))
            result = public(db.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone())
    except BaseException:
        if child is not None:
            child.kill()
            child.wait()
        raise
    # Reap completed children while keeping the launch independent of request life.
    Thread(target=child.wait, daemon=True).start()
    return result


def status(sid: str) -> list[dict]:
    if not database_path(sid).exists():
        return []
    with transaction(sid) as db:
        refresh(db)
        return [{**public(row), 'version': row['version'], 'labeler': row['labeler']}
                for row in db.execute('SELECT * FROM runs ORDER BY started_at, rowid')]


def request(sid: str, run_id: str, action: Literal['pause', 'resume', 'stop']) -> dict:
    if action not in ('pause', 'resume', 'stop'):
        raise ValueError('Invalid worker action')
    with transaction(sid) as db:
        refresh(db)
        row = db.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        if row['state'] in ACTIVE:
            db.execute('UPDATE runs SET action=? WHERE run_id=?', (action, run_id))
        return public(row)
