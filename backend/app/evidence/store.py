"""Version-local evidence rows (D-251).

Scoped writes replace their owner/context/tab atomically. JSON fields accept
SQL names or decoded names and are returned decoded. Run/writable-version
checks belong to the caller, as in SegmentStore.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3

from app.context import store as sessions
from app.context.versions import version_dir

_SCHEMA = '''
CREATE TABLE IF NOT EXISTS meta (run TEXT NOT NULL, params_json TEXT NOT NULL, started_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS queries (
    owner TEXT NOT NULL, dim TEXT NOT NULL, text TEXT NOT NULL, origin TEXT NOT NULL,
    PRIMARY KEY (owner, dim));
CREATE TABLE IF NOT EXISTS candidates (
    context_id TEXT NOT NULL, doc_id TEXT NOT NULL, relevance REAL,
    dims_hit_json TEXT, band TEXT, known_excluded TEXT,
    round DEFAULT 0, PRIMARY KEY (context_id, doc_id));
CREATE TABLE IF NOT EXISTS selected (
    context_id TEXT NOT NULL, tab TEXT NOT NULL CHECK(tab IN ('all','new')),
    rank INTEGER NOT NULL, doc_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('support','counter','rare')),
    quality REAL, novelty TEXT, novelty_reason TEXT,
    PRIMARY KEY (context_id, tab, role, doc_id));
CREATE TABLE IF NOT EXISTS contexts (
    context_id TEXT PRIMARY KEY, persona_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('queued','running','done','failed','skipped')),
    error TEXT, coverage INTEGER, counts_json TEXT, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS persona_support (
    persona_id TEXT NOT NULL, rank INTEGER NOT NULL, doc_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('desire','artifact')),
    PRIMARY KEY (persona_id, kind, doc_id));
'''
_ORDERS = {'queries': 'owner, dim', 'candidates': 'context_id, relevance DESC, doc_id',
           'selected': 'context_id, tab, rank, role, doc_id', 'contexts': 'context_id',
           'persona_support': 'persona_id, rank, kind, doc_id'}


def _decode(row):
    return {key[:-5] if key.endswith('_json') else key:
            json.loads(value) if key.endswith('_json') and value is not None else value
            for key, value in dict(row).items()}


@dataclass(frozen=True)
class EvidenceSnapshot:
    """Detached rows read with their run and params in one SQLite transaction."""
    run: str | None
    params: dict
    started_at: str | None
    queries: list[dict]
    candidates: list[dict]
    selected: list[dict]
    contexts: list[dict]
    persona_support: list[dict]


class EvidenceStore:
    def __init__(self, directory):
        self.path = Path(directory) / 'evidence' / 'evidence.sqlite'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            if db.execute('PRAGMA user_version').fetchone()[0] < 1:
                db.executescript(_SCHEMA)
                db.execute('PRAGMA user_version=1')
            self._columns = {table: {row['name'] for row in db.execute(f'PRAGMA table_info({table})')}
                             for table in _ORDERS}

    @classmethod
    def open(cls, sid: str, version: str) -> 'EvidenceStore':
        return cls(version_dir(sid, version))

    @contextmanager
    def _db(self, *, write=False):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _encode(self, table, values):
        encoded = {}
        for key, value in values.items():
            column = key if key in self._columns[table] else key + '_json'
            if column not in self._columns[table]:
                raise ValueError(f'Unknown {table} field: {key}')
            if column.endswith('_json') and value is not None:
                value = json.dumps(json.loads(value) if isinstance(value, str) else value, ensure_ascii=False)
            encoded[column] = value
        return encoded

    def reset(self, run: str, params: dict) -> None:
        if not isinstance(run, str) or not run:
            raise ValueError('run must be a nonempty string')
        with self._db(write=True) as db:
            for table in ('meta', *_ORDERS):
                db.execute(f'DELETE FROM {table}')
            db.execute('INSERT INTO meta VALUES (?, ?, ?)',
                       (run, json.dumps(params, ensure_ascii=False), sessions.now()))

    def get_run(self) -> str | None:
        with self._db() as db:
            row = db.execute('SELECT run FROM meta').fetchone()
            return row['run'] if row else None

    def _replace(self, table, scope, rows):
        # Validate/serialize before taking the writer lock; insertion failures
        # still roll back both the deletion and every inserted row.
        encoded = []
        for row in rows:
            if any(key in row and row[key] != value for key, value in scope.items()):
                raise ValueError('Row does not match write scope')
            encoded.append(self._encode(table, {**row, **scope}))
        where = ' AND '.join(f'{key}=?' for key in scope)
        with self._db(write=True) as db:
            db.execute(f'DELETE FROM {table} WHERE {where}', tuple(scope.values()))
            for values in encoded:
                columns, placeholders = ', '.join(values), ', '.join('?' for _ in values)
                db.execute(f'INSERT INTO {table} ({columns}) VALUES ({placeholders})', tuple(values.values()))

    def _read(self, db, table, scope=None):
        scope = scope or {}
        where = ' WHERE ' + ' AND '.join(f'{key}=?' for key in scope) if scope else ''
        return [_decode(row) for row in db.execute(
            f'SELECT * FROM {table}{where} ORDER BY {_ORDERS[table]}', tuple(scope.values()))]

    def _list(self, table, **scope):
        with self._db() as db:
            return self._read(db, table, {key: value for key, value in scope.items() if value is not None})

    def write_queries(self, owner: str, rows: list[dict]) -> None:
        self._replace('queries', {'owner': owner}, rows)

    def queries(self, owner: str | None = None) -> list[dict]:
        return self._list('queries', owner=owner)

    def write_candidates(self, context_id: str, rows: list[dict]) -> None:
        self._replace('candidates', {'context_id': context_id}, rows)

    def candidates(self, context_id: str) -> list[dict]:
        return self._list('candidates', context_id=context_id)

    def write_selected(self, context_id: str, tab: str, rows: list[dict]) -> None:
        if tab not in {'all', 'new'}:
            raise ValueError('Invalid evidence tab')
        self._replace('selected', {'context_id': context_id, 'tab': tab}, rows)

    def selected(self, context_id: str, tab: str | None = None) -> list[dict]:
        return self._list('selected', context_id=context_id, tab=tab)

    def set_context(self, context_id: str, persona_id: str, status: str, **fields) -> None:
        values = self._encode('contexts', {**fields, 'context_id': context_id,
                              'persona_id': persona_id, 'status': status, 'updated_at': sessions.now()})
        columns, placeholders = ', '.join(values), ', '.join('?' for _ in values)
        updates = ', '.join(f'{key}=excluded.{key}' for key in values if key != 'context_id')
        with self._db(write=True) as db:
            db.execute(f'INSERT INTO contexts ({columns}) VALUES ({placeholders}) '
                       f'ON CONFLICT(context_id) DO UPDATE SET {updates}', tuple(values.values()))

    def patch_counts(self, context_id, **fields):
        """Merge only owned counters against the current row in one transaction."""
        with self._db(write=True) as db:
            row = db.execute('SELECT counts_json FROM contexts WHERE context_id=?', (context_id,)).fetchone()
            if row:
                counts = {**json.loads(row['counts_json'] or '{}'), **fields}
                db.execute('UPDATE contexts SET counts_json=? WHERE context_id=?',
                           (json.dumps(counts), context_id))

    def contexts(self) -> list[dict]:
        return self._list('contexts')

    def write_persona_support(self, persona_id: str, rows: list[dict]) -> None:
        self._replace('persona_support', {'persona_id': persona_id}, rows)

    def snapshot(self) -> EvidenceSnapshot:
        with self._db() as db:
            db.execute('BEGIN')
            row = db.execute('SELECT * FROM meta').fetchone()
            meta = _decode(row) if row else dict(run=None, params={}, started_at=None)
            return EvidenceSnapshot(**meta, **{table: self._read(db, table) for table in _ORDERS})
