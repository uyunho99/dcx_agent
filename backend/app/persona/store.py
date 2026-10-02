"""Version-local stage-eight JSON files and full revision snapshots.

History includes the current revision, with an independent items snapshot in
each entry. Mutations acquire the session lock internally; callers must not
hold that lock. Every mutation checks the selected version while locked.
Callers may supply an additional source-generation publication guard.
Reads never create files or directories.
"""
import json
import os
from pathlib import Path

from app.context import store as sessions
from app.context.versions import version_dir


_NAMES = frozenset(('cards', 'map', 'tree', 'insights', 'concepts', 'stage_8'))


def _concept_identity(row):
    # Relative ranks and session aggregates are not concept source identity.
    return {key: row.get(key) for key in ('id', 'title', 'pain_point', 'context_ids')} if row else None


class PersonaStore:
    def __init__(self, sid: str, path: Path, version=None):
        self.sid = sid
        self.path = path
        self.version = version
        self.guard = None

    @classmethod
    def open(cls, sid, version) -> 'PersonaStore':
        return cls(sid, version_dir(sid, version) / 'persona', version)

    def _file(self, name: str) -> Path:
        if name not in _NAMES:
            raise sessions.StoreError('Invalid persona file name', 400, 'validation')
        return self.path / f'{name}.json'

    def read(self, name: str) -> dict | None:
        document = sessions.read_json(self._file(name))
        if name == 'concepts' and document:
            self._check_concept_sources(document.get('items', []))
        return document

    def write(self, name: str, data: dict) -> None:
        path = self._file(name)
        with sessions.locked(self.sid):
            sessions.assert_writable(self.sid, self.version)
            sessions.write_json(path, data)

    def _new_revision(self, name, current, items, *, by, message):
        """Caller holds the session lock across reading and replacing the file."""
        if self.guard is not None:
            self.guard()
        if name == 'concepts':
            self._check_concept_sources(items)
        revision = current.get('revision', 0) + 1
        entry = dict(revision=revision, items=items, at=sessions.now(),
                     by=by, message=message)
        data = {**current, 'revision': revision, 'items': items,
                'history': [*current.get('history', []), entry]}
        sessions.write_json(self._file(name), data)
        if name == 'insights':
            self._invalidate_concepts(current.get('items', []), items)
        return revision

    def new_revision(self, name: str, items, *, by: str, message: str | None) -> int:
        with sessions.locked(self.sid):
            sessions.assert_writable(self.sid, self.version)
            return self._new_revision(name, self.read(name) or {}, items,
                                      by=by, message=message)

    def revert(self, name: str, revision: int) -> int:
        with sessions.locked(self.sid):
            sessions.assert_writable(self.sid, self.version)
            current = self.read(name) or {}
            snapshot = next((entry for entry in current.get('history', [])
                             if entry['revision'] == revision), None)
            if snapshot is None:
                raise sessions.StoreError('Revision not found', 404, 'not_found')
            return self._new_revision(name, current, snapshot['items'],
                                      by='revert', message=None)

    def append_chat(self, row: dict) -> None:
        # Serialize before opening so invalid input cannot leave a partial row.
        line = json.dumps(row, ensure_ascii=False) + '\n'
        with sessions.locked(self.sid):
            sessions.assert_writable(self.sid, self.version)
            self.path.mkdir(parents=True, exist_ok=True)
            with (self.path / 'chat.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(line)
                stream.flush()
                os.fsync(stream.fileno())

    def _invalidate_concepts(self, previous, items):
        """Keep history intact and invalidate only changed/removed source items."""
        document = self.read('concepts')
        if not document:
            return
        old = {row.get('id'): row for row in previous}
        active = {row.get('id'): row for row in items}
        for concept in document.get('items', []):
            key = concept.get('insight_id', concept.get('id'))
            if key not in active or _concept_identity(old.get(key)) != _concept_identity(active[key]):
                concept['outdated'] = True
        sessions.write_json(self._file('concepts'), document)

    def write_aux(self, name, value):
        if name not in ('checkpoint', 'llm_calls'):
            raise ValueError('Invalid auxiliary file')
        with sessions.locked(self.sid):
            sessions.assert_writable(self.sid, self.version)
            sessions.write_json(self.path / f'{name}.json', value)

    def _check_concept_sources(self, items):
        insights = self.read('insights') or {}
        active = {row.get('id'): row for row in insights.get('items', [])}
        for concept in items:
            key = concept.get('insight_id', concept.get('id'))
            revision = concept.get('insight_revision')
            if revision is None:
                continue  # legacy concepts are invalidated on the next insight edit
            source = next((row for entry in insights.get('history', [])
                           if entry['revision'] == revision for row in entry['items']
                           if row.get('id') == key), None)
            if revision == insights.get('revision'):
                source = active.get(key)
            if (key not in active or _concept_identity(source) != _concept_identity(active[key]) or
                    concept.get('context_ids') != active[key].get('context_ids')):
                concept['outdated'] = True
