"""Durable run storage and public status projection."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time

from app.config import settings
from app.work.proc import pid_alive

HEARTBEAT_INTERVAL = 10
STALE_AFTER_S = 60
ACTIVE = ('running', 'paused')


def database_path(sid: str) -> Path:
    if not sid or sid in ('.', '..') or Path(sid).name != sid:
        raise ValueError('Invalid session ID')
    return Path(settings.local_data_dir).resolve() / 'work' / sid / 'runs.sqlite'


@contextmanager
def transaction(sid):
    path = database_path(sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        db.execute('BEGIN IMMEDIATE')
        db.execute('''CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY, version TEXT NOT NULL, kind TEXT NOT NULL,
            labeler TEXT, args_json TEXT NOT NULL, pid INTEGER NOT NULL,
            state TEXT NOT NULL, progress REAL NOT NULL DEFAULT 0,
            detail TEXT NOT NULL DEFAULT '{}', heartbeat_at REAL NOT NULL,
            error TEXT, action TEXT, started_at REAL NOT NULL)''')
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def refresh(db):
    for row in db.execute("SELECT * FROM runs WHERE state IN ('running','paused')").fetchall():
        if not pid_alive(row['pid']) or row['heartbeat_at'] < time.time() - STALE_AFTER_S:
            db.execute("UPDATE runs SET state='interrupted' WHERE run_id=?", (row['run_id'],))


def public(row):
    return dict(kind=row['kind'], runId=row['run_id'], state=row['state'],
                progress=row['progress'], detail=json.loads(row['detail']),
                heartbeatAt=row['heartbeat_at'], error=row['error'])
