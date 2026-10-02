"""Join stage-five labels to immutable preparation data and cache noun tokens."""
from collections import Counter
from dataclasses import dataclass
import fcntl
import json

import numpy as np

from app.context import store
from app.context.versions import version_dir
from app.known.filter import read_export
from app.model.infer import prepared_root
from app.prep.tokens import tokenize
from app.vectors.store import VectorStore


@dataclass
class SegmentInput:
    ids: list[str]
    vectors: np.ndarray
    tokens: dict[str, list[str]]
    nouns: dict[str, list[str]]
    docs: dict[str, dict]
    report: dict


_SHARD_ROWS = 5000
_VECTOR_BATCH = 10000


def _text(doc):
    return '\n'.join([doc.get('title') or '', doc.get('body') or '',
                      *(comment.get('text') or '' for comment in doc.get('comments', []))])


def _rows(path):
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def _join(export, prepared):
    # Preserve every label/export field, but take original text and collection
    # metadata exclusively from preparation. In particular, an absent channel
    # must never fall back to the judging origin.
    doc = {**prepared, **export, 'judge_source': export.get('source')}
    for key in ('title', 'body', 'source', 'author_hash', 'date'):
        doc[key] = prepared.get(key, '')
    doc['comments'] = prepared.get('comments', [])
    return doc


def _selected(root, folder, ids, field=None):
    return {row['doc_id']: row[field] if field else row
            for path in sorted((root / folder).glob('*.jsonl'))
            for row in _rows(path) if row['doc_id'] in ids}


def _nouns(root, ids, pulse=None):
    """Cache all prepared nouns, retaining only requested IDs and one shard.

    The manifest is published last under a dedicated cache lock. Validate all
    cache rows while streaming, so damaged unselected shards are rebuilt too.
    """
    pulse = pulse or (lambda **detail: None)
    paths = sorted((root / 'docs').glob('*.jsonl'))
    prep = store.read_json(root / 'manifest.json') or {}
    total = prep.get('counts', {}).get('after')
    if total is None:
        total = sum(1 for path in paths for _ in _rows(path))
    pulse(docs=0, total=total)
    directory = root / 'nouns'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            manifest = store.read_json(directory / 'manifest.json') or {}
            if manifest.get('status') == 'done' and manifest.get('count') == total:
                cached, count = {}, 0
                for name in manifest['parts']:
                    for row in _rows(directory / name):
                        words = row['nouns']
                        if not isinstance(words, list) or not all(isinstance(w, str) for w in words):
                            raise ValueError('Invalid noun cache')
                        if row['doc_id'] in ids:
                            cached[row['doc_id']] = words
                        count += 1
                    pulse(docs=count, total=total)
                if count == total and ids <= cached.keys():
                    return cached
        except (OSError, ValueError, KeyError, TypeError):
            pass
        (directory / 'manifest.json').unlink(missing_ok=True)
        for path in directory.glob('part-*.jsonl'):
            path.unlink()
        pos = prep.get('config', {}).get('tokenPos', [])
        nouns_only = bool(pos) and all(tag.startswith('NN') for tag in pos)
        cached, parts, batch, count = {}, [], [], 0
        for path in paths:
            # Preparation publishes matching docs/tokens shards.
            token_path = root / 'tokens' / path.name
            tokens = iter(_rows(token_path)) if nouns_only and token_path.exists() else iter(())
            for doc in _rows(path):
                doc_id = doc['doc_id']
                token_row = next(tokens, {})
                words = (list(token_row['tokens']) if token_row.get('doc_id') == doc_id
                         else tokenize(_text(doc), ('NNG', 'NNP')))
                if doc_id in ids:
                    cached[doc_id] = words
                batch.append(dict(doc_id=doc_id, nouns=words))
                count += 1
                pulse(docs=count, total=total)
                if len(batch) == _SHARD_ROWS:
                    _write_part(directory, parts, batch)
                    batch = []
        if batch:
            _write_part(directory, parts, batch)
        store.write_json(directory / 'manifest.json', dict(status='done', count=count, parts=parts))
        return cached


def restore_input(sid, version, saved, vectors, pulse=None):
    """Rehydrate the compact checkpoint from immutable preparation shards."""
    data = store.read_json(version_dir(sid, version) / 'session.json')
    root = prepared_root(sid, data)
    ids = saved['ids']
    selected = set(ids)
    prepared = _selected(root, 'docs', selected)
    relevant = {r['doc_id']: r for r in read_export(sid, data) if r['doc_id'] in selected}
    return SegmentInput(ids, vectors, _selected(root, 'tokens', selected, 'tokens'),
                        _nouns(root, selected, pulse),
                        {i: _join(relevant[i], prepared[i]) for i in ids}, saved['report'])


def _write_part(directory, parts, rows):
    name = f'part-{len(parts) + 1:05d}.jsonl'
    store.atomic_write(directory / name, ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
    parts.append(name)


class _SelectedVectors(VectorStore):
    """Stream the collection index; retain selected records and shard sizes."""

    def __init__(self, root, ids):
        super().__init__(root)
        self.selected, self.sizes = {}, Counter()
        if self.index.exists():
            for row in _rows(self.index):
                self.sizes[row['shard']] += 1
                if row['doc_id'] in ids:
                    self.selected[row['doc_id']] = row

    def get(self, doc_ids):
        from app.config import settings
        selected = [self.selected[i] for i in doc_ids if i in self.selected]
        dim = settings.embed_dim
        if self.sizes:
            first = next(iter(self.sizes))
            dim = self._vectors(first, self.sizes[first]).shape[1]
        values = np.empty((len(selected), dim), dtype=np.float32)
        for i, row in enumerate(selected):
            values[i] = self._vectors(row['shard'], self.sizes[row['shard']])[row['row']]
        return [r['doc_id'] for r in selected], values


def load_input(sid: str, version: str, *, pulse=None) -> SegmentInput:
    data = store.read_json(version_dir(sid, version) / 'session.json')
    if data is None:
        raise store.StoreError('Session not found', 404, 'not_found')
    relevant = read_export(sid, data)
    root = prepared_root(sid, data)
    selected = {r['doc_id'] for r in relevant}
    prepared = _selected(root, 'docs', selected)
    paths = sorted((root / 'tokens').glob('*.jsonl'))
    if not paths:
        raise store.StoreError('형태소 토큰이 없습니다. 3단계 전처리를 다시 실행하세요.')
    tokens = _selected(root, 'tokens', selected, 'tokens')
    nouns = _nouns(root, selected, pulse)
    ids, joined, selected_tokens, selected_nouns = [], {}, {}, {}
    report = dict(relevant=len(relevant), zero_vector=0, no_tokens=0, truncated=0, by_channel={})
    vectors = _SelectedVectors(root, selected)
    # Keep the full result float16; only one normalization batch is float32.
    output = None
    count = 0
    for start in range(0, len(relevant), _VECTOR_BATCH):
        batch = relevant[start:start + _VECTOR_BATCH]
        found, values = vectors.get([row['doc_id'] for row in batch])
        if output is None:
            output = np.empty((len(relevant), values.shape[1]), dtype=np.float16)
        lookup = {doc_id: i for i, doc_id in enumerate(found)}
        norms = np.linalg.norm(values, axis=1)
        for row in batch:
            doc_id = row['doc_id']
            if doc_id not in prepared:
                raise store.StoreError('전처리 문서를 찾을 수 없습니다.')
            doc = _join(row, prepared[doc_id])
            index = lookup.get(doc_id)
            if index is None or not np.isfinite(norms[index]) or norms[index] == 0:
                report['zero_vector'] += 1
                continue
            if not tokens.get(doc_id):
                report['no_tokens'] += 1
                continue
            report['truncated'] += int(len(_text(doc)) > 2000)
            output[count] = values[index] / norms[index]
            count += 1
            ids.append(doc_id)
            joined[doc_id] = doc
            selected_tokens[doc_id] = tokens[doc_id]
            selected_nouns[doc_id] = nouns[doc_id]
    if output is None:
        _, empty = vectors.get([])
        output = np.empty(empty.shape, dtype=np.float16)
    report['by_channel'] = dict(Counter(doc.get('source', '') for doc in joined.values()))
    return SegmentInput(ids, output[:count], selected_tokens, selected_nouns, joined, report)
