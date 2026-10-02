"""Version-local stage-eight JSON files and full revision snapshots.

History includes the current revision, with an independent items snapshot in
each entry. Mutations acquire the session lock internally; callers must not
hold that lock. API writable-version, run, and content validation belong to the
caller, as in SegmentStore. Reads never create files or directories.
"""
import json
import os
from pathlib import Path

from app.context import store as sessions
from app.context.versions import version_dir


_NAMES = frozenset(('cards', 'map', 'tree', 'insights', 'concepts', 'stage_8'))


class PersonaStore:
    def __init__(self, sid: str, path: Path):
        self.sid = sid
        self.path = path

    @classmethod
    def open(cls, sid, version) -> 'PersonaStore':
        return cls(sid, version_dir(sid, version) / 'persona')

    def _file(self, name: str) -> Path:
        if name not in _NAMES:
            raise sessions.StoreError('Invalid persona file name', 400, 'validation')
        return self.path / f'{name}.json'

    def read(self, name: str) -> dict | None:
        return sessions.read_json(self._file(name))

    def write(self, name: str, data: dict) -> None:
        path = self._file(name)
        with sessions.locked(self.sid):
            sessions.write_json(path, data)

    def _new_revision(self, name, current, items, *, by, message):
        """Caller holds the session lock across reading and replacing the file."""
        revision = current.get('revision', 0) + 1
        entry = dict(revision=revision, items=items, at=sessions.now(),
                     by=by, message=message)
        data = {**current, 'revision': revision, 'items': items,
                'history': [*current.get('history', []), entry]}
        sessions.write_json(self._file(name), data)
        return revision

    def new_revision(self, name: str, items, *, by: str, message: str | None) -> int:
        with sessions.locked(self.sid):
            return self._new_revision(name, self.read(name) or {}, items,
                                      by=by, message=message)

    def revert(self, name: str, revision: int) -> int:
        with sessions.locked(self.sid):
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
            self.path.mkdir(parents=True, exist_ok=True)
            with (self.path / 'chat.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(line)
                stream.flush()
                os.fsync(stream.fileno())
