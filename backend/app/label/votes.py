"""Version-independent durable votes and process-owned pending leases."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import time

from app.work.proc import pid_alive


class VoteCache:
    def __init__(self, root):
        self.path = Path(root) / 'votes.sqlite'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = None
        with self._db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS votes (
                doc_id TEXT PRIMARY KEY, payload_json TEXT,
                status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT, run_id TEXT, at REAL)''')
            db.execute('CREATE INDEX IF NOT EXISTS votes_pending ON votes(status, run_id)')
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

    def seed(self, doc_ids):
        with self._db() as db:
            db.executemany('INSERT OR IGNORE INTO votes(doc_id) VALUES (?)', ((i,) for i in doc_ids))

    def lease(self, n, run_id):
        if n <= 0:
            raise ValueError('Lease size must be positive')
        self.run_id = run_id
        with self._db() as db:
            for owner in db.execute('SELECT * FROM owners').fetchall():
                if not pid_alive(owner['pid']):
                    db.execute("UPDATE votes SET run_id=NULL WHERE run_id=? AND status='pending'", (owner['run_id'],))
                    db.execute('DELETE FROM owners WHERE run_id=?', (owner['run_id'],))
            owner = db.execute('SELECT pid FROM owners WHERE run_id=?', (run_id,)).fetchone()
            if owner and owner['pid'] != os.getpid():
                raise ValueError('Run already owned by another process')
            db.execute('INSERT OR IGNORE INTO owners VALUES (?,?)', (run_id, os.getpid()))
            ids = [r['doc_id'] for r in db.execute("SELECT doc_id FROM votes WHERE status='pending' AND run_id IS NULL ORDER BY doc_id LIMIT ?", (n,))]
            db.executemany('UPDATE votes SET run_id=?, at=? WHERE doc_id=?', ((run_id, time.time(), i) for i in ids))
            return ids

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
