"""Version-local labels and append-only, immediately committed human judgments."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time

from app.label.schema import Label, Tags


class LabelStore:
    def __init__(self, version_dir):
        self.path = Path(version_dir) / 'labels.sqlite'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS final (
                doc_id TEXT PRIMARY KEY, level TEXT NOT NULL,
                confidence REAL NOT NULL, source TEXT NOT NULL, route TEXT NOT NULL,
                tags_json TEXT NOT NULL, reason_code TEXT, signal TEXT,
                rule_version TEXT NOT NULL, questions_version TEXT NOT NULL,
                votes_json TEXT NOT NULL, disagree_json TEXT NOT NULL,
                grade_mismatch INTEGER NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS human (
                doc_id TEXT NOT NULL, labeler TEXT NOT NULL,
                mode TEXT NOT NULL CHECK(mode IN ('escalate', 'audit', 'reissue')),
                tags_json TEXT NOT NULL, reason_code TEXT, signal TEXT,
                submitted_at REAL NOT NULL)''')
            db.execute('CREATE INDEX IF NOT EXISTS human_doc ON human(doc_id, submitted_at)')
            db.execute('''CREATE TABLE IF NOT EXISTS audit_set (
                round INTEGER NOT NULL, doc_id TEXT NOT NULL, picked_at REAL NOT NULL,
                PRIMARY KEY(round, doc_id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS queue (
                doc_id TEXT PRIMARY KEY, reason TEXT NOT NULL, priority REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'open')''')
            db.execute('CREATE INDEX IF NOT EXISTS queue_next ON queue(status, priority, doc_id)')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None, uri=True)
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

    def submit(self, doc_id, labeler, mode, tags):
        """Append one independent judgment; return only after its commit."""
        if mode not in ('escalate', 'audit', 'reissue'):
            raise ValueError('Unknown human labeling mode')
        if not isinstance(doc_id, str) or not doc_id or not isinstance(labeler, str) or not labeler:
            raise ValueError('Document and labeler must be nonempty strings')
        tags = Tags.model_validate(tags.model_dump() if isinstance(tags, Tags) else tags)
        with self._db() as db:
            db.execute('''INSERT INTO human
                (doc_id, labeler, mode, tags_json, reason_code, signal, submitted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (doc_id, labeler, mode, tags.model_dump_json(), tags.reason_code,
                 tags.signal, time.time()))

    def get(self, doc_id) -> Label | None:
        with self._db() as db:
            row = db.execute('SELECT * FROM final WHERE doc_id=?', (doc_id,)).fetchone()
        if row is None:
            return None
        return Label(**json.loads(row['tags_json']), doc_id=row['doc_id'],
                     evidence_level=row['level'], confidence=row['confidence'],
                     source=row['source'], route=row['route'],
                     votes=json.loads(row['votes_json']), rule_version=row['rule_version'],
                     questions_version=row['questions_version'])
