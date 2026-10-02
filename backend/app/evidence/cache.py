"""Preparation-scoped tag and per-Known-Insight judgments, outside versions.

Callers pass session['prep']['derivedRef']['prepKey'], just as segment.dims
uses it. The preparation root helper validates that key without requiring an
active version (old versions share the same cache). Missing known pairs mean
unjudged; a cached False remains a hit. Adding a KI leaves existing pairs alone.
"""
from collections.abc import Iterable
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from app.config import settings
from app.context.store import root_dir
from app.model.infer import prepared_root

PROMPT_DIR = Path(__file__).with_name('prompts')
_SCHEMA = '''
CREATE TABLE IF NOT EXISTS tags (
    doc_id TEXT PRIMARY KEY, tags_json TEXT NOT NULL, model TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS known (
    doc_id TEXT NOT NULL, ki_id TEXT NOT NULL, match INTEGER NOT NULL CHECK(match IN (0,1)),
    model TEXT NOT NULL, PRIMARY KEY (doc_id, ki_id));
CREATE INDEX IF NOT EXISTS known_ki ON known(ki_id);
'''


def prompt_version(name: str, *, prompt_dir: Path | None = None) -> str:
    """Hash exact prompt bytes; prompt_dir supports temporary prompts in tests."""
    if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
        raise ValueError('Invalid prompt name')
    path = (Path(prompt_dir) if prompt_dir is not None else PROMPT_DIR) / f'{name}.v1.md'
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def known_key(item):
    text = item.get('text') or item.get('summary') or ''
    fingerprint = hashlib.sha256(json.dumps([item.get('type'), text, item.get('doc_id')], ensure_ascii=False).encode()).hexdigest()
    return item['id'] + ':' + fingerprint


def known_snapshot(items):
    return {item['id']: known_key(item) for item in items}


class TagCache:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            if db.execute('PRAGMA user_version').fetchone()[0] < 1:
                db.executescript(_SCHEMA)
                db.execute('PRAGMA user_version=1')

    @classmethod
    def open(cls, sid: str, prep_key: str, pver: str) -> 'TagCache':
        root_dir(sid)  # Use the same session validation as version-local stores.
        # No collection ID is needed by this cache. c1 is a validation-only
        # reference: prepared_root does not read or create a collection.
        prepared_root(sid, {'prep': {'status': 'done', 'derivedRef': {
            'collectionId': 'c1', 'prepKey': prep_key}}})
        if not re.fullmatch(r'[0-9a-f]{12}', pver):
            raise ValueError('Invalid prompt version')
        return cls(Path(settings.local_data_dir) / 'llmcache' / sid / prep_key / f'tag-{pver}.sqlite')

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

    def get_tags(self, doc_ids: Iterable[str]) -> dict[str, dict]:
        result = {}
        with self._db() as db:
            db.execute('BEGIN')
            for doc_id in dict.fromkeys(doc_ids):
                row = db.execute('SELECT tags_json, model FROM tags WHERE doc_id=?', (doc_id,)).fetchone()
                if row:
                    result[doc_id] = {**json.loads(row['tags_json']), 'model': row['model']}
        return result

    def put_tags(self, rows: dict[str, dict], model: str) -> None:
        with self._db(write=True) as db:
            db.executemany('INSERT INTO tags VALUES (?, ?, ?) ON CONFLICT(doc_id) '
                           'DO UPDATE SET tags_json=excluded.tags_json, model=excluded.model',
                           [(doc_id, json.dumps({k: v for k, v in tags.items() if k != 'model'}, ensure_ascii=False), model)
                            for doc_id, tags in rows.items()])

    def get_known(self, doc_ids: Iterable[str], ki_ids: Iterable[str]) -> dict[tuple[str, str], bool]:
        wanted = set(ki_ids)
        if not wanted:
            return {}
        result = {}
        with self._db() as db:
            db.execute('BEGIN')
            for doc_id in dict.fromkeys(doc_ids):
                for row in db.execute('SELECT ki_id, match FROM known WHERE doc_id=?', (doc_id,)):
                    if row['ki_id'] in wanted:
                        result[doc_id, row['ki_id']] = bool(row['match'])
        return result

    def put_known(self, rows: dict[tuple[str, str], bool], model: str) -> None:
        with self._db(write=True) as db:
            db.executemany('INSERT INTO known VALUES (?, ?, ?, ?) ON CONFLICT(doc_id, ki_id) '
                           'DO UPDATE SET match=excluded.match, model=excluded.model',
                           [(doc_id, ki_id, int(match), model) for (doc_id, ki_id), match in rows.items()])

    def drop_known(self, ki_id: str) -> None:
        with self._db(write=True) as db:
            db.execute('DELETE FROM known WHERE ki_id=?', (ki_id,))
