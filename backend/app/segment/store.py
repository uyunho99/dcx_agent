"""Version-local stage-six rows.

Writers use SQL column names or decoded JSON names (keywords, goals, ...).
Readers return snake_case rows with decoded JSON fields; theta_json retains
its name to distinguish the full distribution from the scalar theta.
API validation, writable-version checks and run checks belong to the caller.
"""
from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3

import numpy as np

from app.context import store as sessions
from app.context.versions import version_dir


_SCHEMA = '''
CREATE TABLE IF NOT EXISTS docs (
    doc_id TEXT PRIMARY KEY, cluster_id TEXT, persona_id TEXT, context_id TEXT,
    theta REAL, theta_json TEXT, dist_centroid REAL, band TEXT, combo_rarity REAL,
    emerging REAL, lexical_surprise REAL, sentiment REAL, pred_entropy REAL,
    evidence_level TEXT, source TEXT, author_hash TEXT, date TEXT);
CREATE TABLE IF NOT EXISTS clusters (
    cluster_id TEXT PRIMARY KEY, name_draft TEXT, name TEXT, keywords_json TEXT,
    reps_json TEXT, metrics_json TEXT, quality_json TEXT, channels_json TEXT,
    requests_json TEXT, confirmed_at TEXT);
CREATE TABLE IF NOT EXISTS personas (
    persona_id TEXT PRIMARY KEY, cluster_id TEXT, name_draft TEXT, name TEXT,
    desire_draft TEXT, desire TEXT, goals_draft_json TEXT, goals_json TEXT,
    centrality_json TEXT, network_json TEXT, similar_json TEXT, reps_json TEXT, flags_json TEXT DEFAULT '[]',
    confirmed_at TEXT);
CREATE TABLE IF NOT EXISTS contexts (
    context_id TEXT PRIMARY KEY, persona_id TEXT, name_draft TEXT, name TEXT,
    action_draft TEXT, action TEXT, keywords_json TEXT, dominant_constraint TEXT,
    dims_summary_json TEXT, quality_json TEXT, flags_json TEXT, centroid BLOB,
    confirmed_at TEXT);
CREATE TABLE IF NOT EXISTS combos (
    pair TEXT, a_code TEXT, b_code TEXT, count INTEGER,
    PRIMARY KEY (pair, a_code, b_code));
CREATE TABLE IF NOT EXISTS codes (
    dim TEXT, code TEXT, label TEXT, count INTEGER, PRIMARY KEY (dim, code));
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX IF NOT EXISTS docs_context_band ON docs(context_id, band, doc_id);
CREATE INDEX IF NOT EXISTS docs_cluster ON docs(cluster_id);
CREATE INDEX IF NOT EXISTS docs_persona ON docs(persona_id);
CREATE INDEX IF NOT EXISTS personas_cluster ON personas(cluster_id);
CREATE INDEX IF NOT EXISTS contexts_persona ON contexts(persona_id);
'''
_LAYERS = {'clusters': 'cluster_id', 'personas': 'persona_id', 'contexts': 'context_id'}
_CONFIRM = {'clusters': {'name'}, 'personas': {'name', 'desire', 'goals'},
            'contexts': {'name', 'action'}}


def _decode(row):
    result = {}
    for key, value in dict(row).items():
        if key.endswith('_json'):
            result[key if key == 'theta_json' else key[:-5]] = json.loads(value) if value is not None else None
        elif key == 'centroid' and value is not None:
            result[key] = np.frombuffer(value, dtype=np.float32).copy()
        else:
            result[key] = value
    return result


def _natural(value):
    return tuple(int(part) if part.isdigit() else part for part in re.split(r'(\d+)', value))


class SegmentStore:
    def __init__(self, directory):
        self.path = Path(directory) / 'segment' / 'segment.sqlite'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            if db.execute('PRAGMA user_version').fetchone()[0] < 1:
                db.executescript(_SCHEMA)
                if 'flags_json' not in {row['name'] for row in db.execute('PRAGMA table_info(personas)')}:
                    db.execute("ALTER TABLE personas ADD COLUMN flags_json TEXT DEFAULT '[]'")
                db.execute('PRAGMA user_version=1')
            if 'quality_json' not in {r['name'] for r in db.execute('PRAGMA table_info(personas)')}:
                db.execute('ALTER TABLE personas ADD COLUMN quality_json TEXT')
            self._columns = {table: {row['name'] for row in db.execute(f'PRAGMA table_info({table})')}
                             for table in (*_LAYERS, 'docs', 'codes', 'combos')}

    @classmethod
    def open(cls, sid, version):
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
                # Accept existing serialized SQL rows as well as Python values.
                value = json.dumps(json.loads(value) if isinstance(value, str) else value, ensure_ascii=False)
            elif column == 'centroid' and value is not None:
                value = value if isinstance(value, bytes) else np.asarray(value, dtype=np.float32).tobytes()
            encoded[column] = value
        return encoded

    def write_layers(self, clusters=(), personas=(), contexts=(), docs=(), codes=(), combos=()):
        """Atomically replace one complete result, clearing previous confirmations.

        Inputs are iterables of row dictionaries; omitted tables become empty.
        The current run is managed separately via set_run by the orchestrator.
        """
        with self._db(write=True) as db:
            for table, rows in (('docs', docs), ('contexts', contexts), ('personas', personas),
                                ('clusters', clusters), ('codes', codes), ('combos', combos)):
                db.execute(f'DELETE FROM {table}')
                for row in rows:
                    values = self._encode(table, row)
                    columns = ', '.join(values)
                    placeholders = ', '.join('?' for _ in values)
                    db.execute(f'INSERT INTO {table} ({columns}) VALUES ({placeholders})', tuple(values.values()))

    def _list(self, table, parent=None, value=None):
        clause, args = ('', ()) if value is None else (f' WHERE {parent}=?', (value,))
        with self._db() as db:
            rows = [_decode(row) for row in db.execute(f'SELECT * FROM {table}{clause}', args)]
        return sorted(rows, key=lambda row: _natural(row[_LAYERS[table]]))

    def clusters(self):
        return self._list('clusters')

    def personas(self, cluster_id=None):
        return self._list('personas', 'cluster_id', cluster_id)

    def contexts(self, persona_id=None):
        return self._list('contexts', 'persona_id', persona_id)

    def docs(self, context_id=None, band=None, limit=100, offset=0):
        if not isinstance(limit, int) or not isinstance(offset, int) or limit < 0 or offset < 0:
            raise ValueError('limit and offset must be nonnegative integers')
        filters, args = [], []
        for key, value in (('context_id', context_id), ('band', band)):
            if value is not None:
                filters.append(f'{key}=?')
                args.append(value)
        where = ' WHERE ' + ' AND '.join(filters) if filters else ''
        with self._db() as db:
            return [_decode(row) for row in db.execute(
                f'SELECT * FROM docs{where} ORDER BY doc_id LIMIT ? OFFSET ?', (*args, limit, offset))]

    def _confirm(self, db, layer, item_id, values):
        if layer not in _LAYERS or not values or set(values) - _CONFIRM[layer]:
            raise ValueError('Invalid confirmation fields or layer')
        encoded = self._encode(layer, values)
        encoded['confirmed_at'] = sessions.now()
        assignments = ', '.join(f'{key}=?' for key in encoded)
        cursor = db.execute(f'UPDATE {layer} SET {assignments} WHERE {_LAYERS[layer]}=?',
                            (*encoded.values(), item_id))
        if cursor.rowcount != 1:
            raise sessions.StoreError('구획을 찾을 수 없습니다.', 404, 'not_found')
        return _decode(db.execute(f'SELECT * FROM {layer} WHERE {_LAYERS[layer]}=?', (item_id,)).fetchone())

    def confirm(self, layer, id, values):
        with self._db(write=True) as db:
            return self._confirm(db, layer, id, values)

    def confirm_contexts(self, persona_id, items):
        with self._db(write=True) as db:
            result = []
            for item in items:
                item_id = item['id']
                row = db.execute('SELECT persona_id FROM contexts WHERE context_id=?', (item_id,)).fetchone()
                if row is None or row['persona_id'] != persona_id:
                    raise sessions.StoreError('이 Persona에 속하지 않는 Context입니다.', 422, 'validation')
                result.append(self._confirm(db, 'contexts', item_id,
                                            {key: value for key, value in item.items() if key != 'id'}))
            return result

    def add_request(self, layer, id, kind, note):
        if layer != 'clusters' or kind not in {'split', 'merge'}:
            raise ValueError('Only cluster split/merge requests are supported')
        with self._db(write=True) as db:
            row = db.execute('SELECT requests_json FROM clusters WHERE cluster_id=?', (id,)).fetchone()
            if row is None:
                raise sessions.StoreError('클러스터를 찾을 수 없습니다.', 404, 'not_found')
            requests = json.loads(row['requests_json'] or '[]')
            request = dict(layer=layer, id=id, kind=kind, note=note, at=sessions.now())
            requests.append(request)
            db.execute('UPDATE clusters SET requests_json=? WHERE cluster_id=?',
                       (json.dumps(requests, ensure_ascii=False), id))
            return request

    def get_run(self):
        with self._db() as db:
            row = db.execute("SELECT value FROM meta WHERE key='run'").fetchone()
            return row['value'] if row else None

    def set_run(self, run):
        if not isinstance(run, str) or not run:
            raise ValueError('run must be a nonempty string')
        with self._db(write=True) as db:
            db.execute("INSERT INTO meta (key, value) VALUES ('run', ?) "
                       'ON CONFLICT(key) DO UPDATE SET value=excluded.value', (run,))
