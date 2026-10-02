"""Join stage-five labels to immutable preparation data and cache noun tokens."""
from collections import Counter
from dataclasses import dataclass
import fcntl
import json

import numpy as np

from app.context import store
from app.context.versions import version_dir
from app.known.filter import read_export
from app.model.infer import documents, prepared_root
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


def _nouns(root, docs, tokens):
    """Publish the manifest last; no partial generation is ever read.

    Cache all prepared documents, not just this version's relevant subset.
    A dedicated cache lock serializes concurrent builders across versions
    without blocking session writes or reacquiring a caller's session lock.
    """
    directory = root / 'nouns'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            manifest = store.read_json(directory / 'manifest.json') or {}
            if manifest.get('status') == 'done' and manifest.get('count') == len(docs):
                cached = {row['doc_id']: row['nouns'] for name in manifest['parts']
                          for row in _rows(directory / name)}
                if cached.keys() == docs.keys() and all(
                        isinstance(words, list) and all(isinstance(word, str) for word in words)
                        for words in cached.values()):
                    return cached
        except (OSError, ValueError, KeyError, TypeError):
            pass
        (directory / 'manifest.json').unlink(missing_ok=True)
        for path in directory.glob('part-*.jsonl'):
            path.unlink()
        prep = store.read_json(root / 'manifest.json') or {}
        pos = prep.get('config', {}).get('tokenPos', [])
        nouns_only = bool(pos) and all(tag.startswith('NN') for tag in pos)
        cached, parts, batch = {}, [], []
        for doc_id, doc in docs.items():
            words = list(tokens[doc_id]) if nouns_only and doc_id in tokens else tokenize(_text(doc), ('NNG', 'NNP'))
            cached[doc_id] = words
            batch.append(dict(doc_id=doc_id, nouns=words))
            if len(batch) == _SHARD_ROWS:
                _write_part(directory, parts, batch)
                batch = []
        if batch:
            _write_part(directory, parts, batch)
        store.write_json(directory / 'manifest.json', dict(status='done', count=len(cached), parts=parts))
        return cached


def _write_part(directory, parts, rows):
    name = f'part-{len(parts) + 1:05d}.jsonl'
    store.atomic_write(directory / name, ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
    parts.append(name)


def load_input(sid: str, version: str) -> SegmentInput:
    data = store.read_json(version_dir(sid, version) / 'session.json')
    if data is None:
        raise store.StoreError('Session not found', 404, 'not_found')
    relevant = read_export(sid, data)
    root = prepared_root(sid, data)
    prepared = documents(sid, data)
    paths = sorted((root / 'tokens').glob('*.jsonl'))
    if not paths:
        raise store.StoreError('형태소 토큰이 없습니다. 3단계 전처리를 다시 실행하세요.')
    tokens = {row['doc_id']: row['tokens'] for path in paths for row in _rows(path)}
    nouns = _nouns(root, prepared, tokens)
    ids, joined, selected_tokens, selected_nouns = [], {}, {}, {}
    report = dict(relevant=len(relevant), zero_vector=0, no_tokens=0, truncated=0, by_channel={})
    vectors = VectorStore(root)
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
