"""Append-only vector shards. The prepKey directory is the store root.

A single preparation worker writes a root; readers reuse immutable mappings.
The fsynced JSONL index publishes each shard only after its data is durable.
"""
import json
import os
import shutil
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Iterator

import numpy as np

from app.config import settings

SHARD_ROWS = 10_000


@lru_cache(maxsize=32)
def _read_index(path: str, signature: tuple):
    with open(path, encoding='utf-8') as stream:
        return tuple(json.loads(line) for line in stream if line.strip())


@lru_cache(maxsize=256)
def _mapping(path: str, signature: tuple, rows: int):
    dim = signature[0] // (rows * np.dtype(np.float16).itemsize)
    if dim == 0 or signature[0] != rows * dim * 2:
        raise ValueError('Invalid vector shard size')
    return np.memmap(path, dtype=np.float16, mode='r', shape=(rows, dim))


def _signature(path: Path) -> tuple:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class VectorStore:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.directory = self.root / 'vectors'
        self.index = self.directory / 'ids.jsonl'

    def _records(self):
        if not self.index.exists():
            return ()
        return _read_index(str(self.index), _signature(self.index))

    def _groups(self):
        groups = {}
        for record in self._records():
            groups.setdefault(record['shard'], []).append(record)
        return groups

    def _vectors(self, shard, rows):
        path = self.directory / f'shard-{shard:05d}.f16'
        return _mapping(str(path), _signature(path), rows)

    def write_shard(self, ids: list[str], vecs: np.ndarray, failed: list[bool]) -> None:
        vectors = np.asarray(vecs, dtype=np.float32)
        if vectors.ndim != 2 or len(ids) != len(vectors) or len(failed) != len(ids):
            raise ValueError('IDs, vectors and failure flags must have matching rows')
        if vectors.shape[1] <= 0 or not np.isfinite(vectors).all():
            raise ValueError('Vectors must have positive dimension and finite values')
        existing = {record['doc_id'] for record in self._records()}
        if len(set(ids)) != len(ids) or existing.intersection(ids):
            raise ValueError('Document IDs must be unique')
        groups = self._groups()
        if groups:
            shard = next(iter(groups))
            if self._vectors(shard, len(groups[shard])).shape[1] != vectors.shape[1]:
                raise ValueError('Vector dimension does not match store')
        if not ids:
            return
        with np.errstate(over='ignore'):
            encoded = vectors.astype(np.float16)
        encoded[np.asarray(failed, dtype=bool)] = 0
        if not np.isfinite(encoded).all():
            raise ValueError('Vectors exceed float16 range')
        self.directory.mkdir(parents=True, exist_ok=True)
        # Skip orphaned files left by interruption before index publication.
        numbers = [int(path.stem.split('-')[1]) for path in self.directory.glob('shard-*.f16')]
        shard = max(numbers, default=0) + 1
        for start in range(0, len(ids), SHARD_ROWS):
            stop = min(start + SHARD_ROWS, len(ids))
            path = self.directory / f'shard-{shard:05d}.f16'
            with path.open('xb') as stream:
                stream.write(encoded[start:stop].tobytes())
                stream.flush()
                os.fsync(stream.fileno())
            _sync_directory(self.directory)
            records = [dict(doc_id=ids[i], shard=shard, row=i-start, failed=bool(failed[i]))
                       for i in range(start, stop)]
            # Publish the appended index atomically so an interrupted write
            # cannot expose half a shard or a truncated JSON record to readers.
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=self.directory, delete=False) as stream:
                    temporary = Path(stream.name)
                    if self.index.exists():
                        with self.index.open('rb') as previous:
                            shutil.copyfileobj(previous, stream)
                    stream.write(''.join(json.dumps(record, ensure_ascii=False) + '\n'
                                         for record in records).encode('utf-8'))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.index)
                _sync_directory(self.directory)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            shard += 1

    def get(self, doc_ids) -> tuple[list[str], np.ndarray]:
        records = self._records()
        lookup = {record['doc_id']: record for record in records}
        groups = self._groups()
        selected = [lookup[doc_id] for doc_id in doc_ids if doc_id in lookup]
        dim = settings.embed_dim
        if groups:
            shard = next(iter(groups))
            dim = self._vectors(shard, len(groups[shard])).shape[1]
        mappings = {shard: self._vectors(shard, len(groups[shard]))
                    for shard in {record['shard'] for record in selected}}
        vectors = np.empty((len(selected), dim), dtype=np.float32)
        for i, record in enumerate(selected):
            vectors[i] = mappings[record['shard']][record['row']]
        return [record['doc_id'] for record in selected], vectors

    def iter_shards(self) -> Iterator[tuple[list[str], np.ndarray, np.ndarray]]:
        for shard, records in self._groups().items():
            yield ([record['doc_id'] for record in records],
                   np.asarray(self._vectors(shard, len(records)), dtype=np.float32),
                   np.array([record.get('failed', False) for record in records], dtype=bool))

    def count(self) -> int:
        return len(self._records())

    def done_shards(self) -> int:
        return len(self._groups())
