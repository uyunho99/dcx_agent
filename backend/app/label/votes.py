"""Version-independent durable votes and process-owned pending leases."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import time

from app.work.proc import pid_alive
from app.config import settings
from app.work.status import ACTIVE, STALE_AFTER_S, database_path

LEASE_MAX_AGE_S = 600


class VoteCache:
    def __init__(self, root):
        self.path = Path(root) / 'votes.sqlite'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = None
        try:
            self.sid = self.path.resolve().relative_to(
                (Path(settings.local_data_dir) / 'judge').resolve()).parts[0]
        except ValueError:
            # Standalone caches have no associated runs registry.
            self.sid = None
        with self._db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS votes (
                doc_id TEXT PRIMARY KEY, payload_json TEXT,
                status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT, run_id TEXT, at REAL)''')
            db.execute('CREATE INDEX IF NOT EXISTS votes_pending ON votes(status, run_id)')
            if 'priority' not in {r['name'] for r in db.execute('PRAGMA table_info(votes)')}:
                db.execute('ALTER TABLE votes ADD COLUMN priority INTEGER NOT NULL DEFAULT 1')
            db.execute('CREATE TABLE IF NOT EXISTS owners (run_id TEXT PRIMARY KEY, pid INTEGER NOT NULL)')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def seed(self, doc_ids, priorities=None):
        """priorities: optional {doc_id: int}; lower values are leased first."""
        with self._db() as db:
            db.executemany('INSERT OR IGNORE INTO votes(doc_id) VALUES (?)', ((i,) for i in doc_ids))
            if priorities:
                db.executemany('UPDATE votes SET priority=? WHERE doc_id=? AND priority!=?',
                               ((p, i, p) for i, p in priorities.items()))

    def reclaim(self, db, keep=None):
        """Fence dead, inactive, and expired owners inside the claim transaction."""
        runs = None
        if self.sid is not None:
            runs = {}
            path = database_path(self.sid)
            if path.exists():
                with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as work:
                    runs = {r[0]: r[1:] for r in work.execute(
                        'SELECT run_id,pid,state,heartbeat_at FROM runs')}
        now = time.time()
        for owner in db.execute('SELECT * FROM owners').fetchall():
            if keep is not None and owner['run_id'] == keep and owner['pid'] == os.getpid():
                continue  # This live object already holds in-flight batches for this run.
            run = runs.get(owner['run_id']) if runs is not None else None
            inactive = runs is not None and (not run or run[0] != owner['pid']
                or run[1] not in ACTIVE or run[2] < now - STALE_AFTER_S)
            if not pid_alive(owner['pid']) or inactive:
                db.execute("UPDATE votes SET run_id=NULL WHERE run_id=? AND status='pending'", (owner['run_id'],))
                db.execute('DELETE FROM owners WHERE run_id=?', (owner['run_id'],))
        db.execute("""UPDATE votes SET run_id=NULL WHERE status='pending' AND run_id IS NOT NULL
            AND run_id IS NOT ?
            AND (at IS NULL OR at < ? OR NOT EXISTS
                 (SELECT 1 FROM owners WHERE owners.run_id=votes.run_id))""", (keep, now - LEASE_MAX_AGE_S))

    def lease(self, n, run_id):
        if n <= 0:
            raise ValueError('Lease size must be positive')
        keep = run_id if self.run_id == run_id else None  # Only after this object leased before.
        self.run_id = run_id
        with self._db() as db:
            self.reclaim(db, keep)
            owner = db.execute('SELECT pid FROM owners WHERE run_id=?', (run_id,)).fetchone()
            if owner and owner['pid'] != os.getpid():
                raise ValueError('Run already owned by another process')
            db.execute('INSERT OR IGNORE INTO owners VALUES (?,?)', (run_id, os.getpid()))
            ids = [r['doc_id'] for r in db.execute("SELECT doc_id FROM votes WHERE status='pending' AND run_id IS NULL ORDER BY priority, attempts, doc_id LIMIT ?", (n,))]
            db.executemany('UPDATE votes SET run_id=?, at=? WHERE doc_id=?', ((run_id, time.time(), i) for i in ids))
            return ids

    def refresh(self, run_id):
        """Renew this run's pending leases using a thread-local connection."""
        with self._db() as db:
            db.execute("UPDATE votes SET at=? WHERE run_id=? AND status='pending'",
                       (time.time(), run_id))

    def put(self, doc_id, payload):
        raw = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        with self._db() as db:
            db.execute("UPDATE votes SET payload_json=?, status='done', last_error=NULL, run_id=NULL, at=? WHERE doc_id=? AND status='pending' AND run_id IS ?", (raw, time.time(), doc_id, self.run_id))

    def mark_bad(self, doc_id, reason):
        with self._db() as db:
            db.execute("UPDATE votes SET status='bad', last_error=?, run_id=NULL, at=? WHERE doc_id=? AND status='pending' AND run_id IS ?", (reason, time.time(), doc_id, self.run_id))

    def fail(self, doc_id, reason):
        """Count failed documents, including every member of an unusable batch."""
        with self._db() as db:
            db.execute("""UPDATE votes SET attempts=attempts+1,
                status=CASE WHEN attempts+1>=3 THEN 'bad' ELSE 'pending' END,
                last_error=?, run_id=NULL, at=?
                WHERE doc_id=? AND status='pending' AND run_id IS ?""", (reason, time.time(), doc_id, self.run_id))

    def release(self):
        with self._db() as db:
            db.execute("UPDATE votes SET run_id=NULL WHERE status='pending' AND run_id=?", (self.run_id,))
            db.execute('DELETE FROM owners WHERE run_id=?', (self.run_id,))

    def counts(self):
        with self._db() as db:
            return {**dict(pending=0, done=0, bad=0), **{r[0]: r[1] for r in db.execute('SELECT status, count(*) FROM votes GROUP BY status')}}
