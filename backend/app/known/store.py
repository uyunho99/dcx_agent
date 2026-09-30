"""Version-local Known Insight CRUD, serialized with the session lock."""
import os
from pathlib import Path

import numpy as np

from app.config import settings
from app.context import store as sessions
from app.known.models import KnownInsight, read_known
from app.vectors.embedder import get_embedder, EmbedderUnconnected, FakeEmbedder, VoyageEmbedder
from app.vectors.store import VectorStore

UNCONNECTED = '유사도 제외는 임베딩 연결 후 적용됩니다'


def prepared_root(sid, data):
    ref = data.get('prep', {}).get('derivedRef')
    if not ref:
        return None
    from app.routers.prep import _root
    return _root(sid, ref['collectionId'], ref['prepKey'])


def session_embedder(sid, data, factory):
    """Match immutable preparation metadata instead of a changed default."""
    root = prepared_root(sid, data)
    manifest = sessions.read_json(root / 'manifest.json') if root else None
    meta = (manifest or {}).get('embedder', {})
    name = meta.get('name') or data.get('prep', {}).get('config', {}).get('embedder') or settings.embed_backend
    if meta.get('dim', settings.embed_dim) != settings.embed_dim or meta.get('model', settings.embed_model) != settings.embed_model:
        raise EmbedderUnconnected('Preparation embedder configuration does not match')
    if name == settings.embed_backend:
        return factory()
    return FakeEmbedder() if name == 'fake' else VoyageEmbedder()


def _data(sid):
    data = sessions.load_session(sid)
    if data is None:
        raise sessions.StoreError('Session not found', 404, 'not_found')
    return data


def list_known(sid, version=None):
    from app.context import versions
    return read_known(versions._data(sid, version) if version else _data(sid))


def replace_stage0(sid, data, texts):
    """Preserve non-stage0 records and reuse unchanged statement vectors.

    Caller holds the session lock. Match by text so reordering or deletion does
    not cause unnecessary provider calls or change surviving item identities.
    """
    previous = [i for i in read_known(data) if i.origin == 'stage0']
    replacements, changed = [], []
    for text in texts:
        item = next((i for i in previous if i.type == 'statement' and i.text == text), None)
        if item is not None:
            previous.remove(item)
        else:
            item = KnownInsight(type='statement', text=text, origin='stage0')
            changed.append(item)
        replacements.append(item)
    _embed_many(sid, changed)
    # Keep other sources byte-for-byte at the JSON record level.
    preserved = [i for i in data.get('knownInsights', [])
                 if isinstance(i, dict) and i.get('from', 'drawer') != 'stage0']
    return [i.model_dump(by_alias=True) for i in replacements] + preserved


def _save(sid, items):
    sessions._update_locked(sid, {'knownInsights': [i.model_dump(by_alias=True) for i in items]})


def _embed(sid, item):
    _embed_many(sid, [item])


def _embed_many(sid, items):
    if not items:
        return
    try:
        vectors = np.asarray(session_embedder(sid, _data(sid), get_embedder).embed([item.text[:2000] for item in items]), dtype=np.float32)
    except Exception:
        # Provider failures never discard the user's statement. The API exposes
        # an unconnected warning, and a later PATCH can retry the missing row.
        return
    if vectors.shape != (len(items), settings.embed_dim):
        return
    valid = np.isfinite(vectors).all(axis=1) & (np.linalg.norm(vectors, axis=1) > 0)
    if not valid.any():
        return
    path = sessions.session_dir(sid) / 'known_vectors.f16'
    # Publish vector bytes before their row pointer in session.json. Orphaned
    # rows after interruption are harmless and are never reused.
    with path.open('ab') as stream:
        for item, vector, usable in zip(items, vectors, valid):
            if usable:
                item.vectorRow = stream.tell() // (settings.embed_dim * 2)
                stream.write(vector.astype(np.float16).tobytes())
        stream.flush()
        os.fsync(stream.fileno())


def _new(sid, data, values):
    item = KnownInsight.model_validate(values)
    item.vectorRow = None
    if item.type == 'statement':
        item.text = item.text.strip()
        if not item.text:
            raise sessions.StoreError('Known Insight 문장을 입력하세요', 422, 'validation')
        item.doc_id = None
        _embed(sid, item)
    else:
        root = prepared_root(sid, data)
        if not item.doc_id or root is None or not VectorStore(root).get([item.doc_id])[0]:
            raise sessions.StoreError('원문 벡터를 찾을 수 없습니다', 404, 'not_found')
        from app.known.filter import prepared_documents
        doc = prepared_documents(root).get(item.doc_id, {})
        item.text = item.text or doc.get('desc') or doc.get('title') or item.doc_id
    return item


def add(sid, values, version=None):
    with sessions.locked(sid):
        data = sessions.assert_writable(sid, version)
        items = read_known(data)
        item = _new(sid, data, values)
        items.append(item)
        _save(sid, items)
        return item


def update(sid, item_id, patch, version=None):
    with sessions.locked(sid):
        data = sessions.assert_writable(sid, version)
        items = read_known(data)
        for index, item in enumerate(items):
            if item.id == item_id:
                values = {**item.model_dump(by_alias=True), **patch}
                changed = any(values.get(k) != getattr(item, k) for k in ('type', 'text', 'doc_id'))
                retry = item.type == 'statement' and item.vectorRow is None and bool(patch)
                items[index] = _new(sid, data, values) if changed or retry else item
                _save(sid, items)
                return items[index]
        raise sessions.StoreError('Known Insight를 찾을 수 없습니다', 404, 'not_found')


def delete(sid, item_id, version=None):
    with sessions.locked(sid):
        data = sessions.assert_writable(sid, version)
        items = read_known(data)
        remaining = [item for item in items if item.id != item_id]
        if len(remaining) == len(items):
            raise sessions.StoreError('Known Insight를 찾을 수 없습니다', 404, 'not_found')
        _save(sid, remaining)


def initialize(sid):
    """Initialize stage-0 statements and deduplicated same-bk statements once."""
    with sessions.locked(sid):
        data = sessions.assert_writable(sid)
        items = read_known(data)
        seen = {item.text for item in items if item.type == 'statement'}
        bk = data.get('projectContext', {}).get('bk') or data.get('bk')
        for path in sorted((Path(settings.local_data_dir) / 'sessions').iterdir()):
            if path.name == sid or not path.is_dir():
                continue
            previous = sessions.load_session(path.name) or {}
            previous_bk = (previous.get('projectContext') or {}).get('bk') or previous.get('bk')
            if not bk or previous_bk != bk:
                continue
            for item in read_known(previous):
                if item.type == 'statement' and item.text not in seen:
                    items.append(KnownInsight(type='statement', text=item.text, origin='prev_session'))
                    seen.add(item.text)
        _embed_many(sid, [item for item in items
                          if item.type == 'statement' and item.vectorRow is None])
        _save(sid, items)


def known_vectors(sid, items, vectors, version_dir=None):
    _, docs = vectors.get([item.doc_id for item in items if item.type == 'doc' and item.doc_id])
    result = list(docs)
    path = (version_dir if version_dir is not None else sessions.session_dir(sid)) / 'known_vectors.f16'
    if path.exists():
        stored = np.fromfile(path, dtype=np.float16).reshape(-1, settings.embed_dim)
        result.extend(stored[item.vectorRow].astype(np.float32) for item in items
                      if item.type == 'statement' and item.vectorRow is not None and 0 <= item.vectorRow < len(stored))
    return np.asarray(result, dtype=np.float32).reshape(-1, settings.embed_dim)
