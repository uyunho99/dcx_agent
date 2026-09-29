"""Append-only P4 shards. Durability precedes queue completion."""
import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)


class DocWriter:
    def __init__(self, dir, shard_size=5000):
        if shard_size < 1:
            raise ValueError('shard_size must be positive')
        self.dir = Path(dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.shard_size = shard_size
        shards = sorted(self.dir.glob('shard-*.jsonl'))
        self.index = int(shards[-1].stem.split('-')[1]) if shards else 1
        self.stream = None
        self._open()

    def _open(self):
        path = self.dir / f'shard-{self.index:04d}.jsonl'
        self.stream = path.open('a+b')
        self.stream.seek(0)
        self.count = sum(1 for _ in self.stream)
        self.stream.seek(0, os.SEEK_END)
        if self.stream.tell():
            self.stream.seek(-1, os.SEEK_END)
            if self.stream.read(1) != b'\n':
                self.stream.write(b'\n')
        self.stream.seek(0, os.SEEK_END)

    def write(self, doc):
        if self.count >= self.shard_size:
            self.flush_and_fsync()
            self.stream.close()
            self.index += 1
            self._open()
        data = doc.model_dump(mode='json') if hasattr(doc, 'model_dump') else doc
        self.stream.write((json.dumps(data, ensure_ascii=False) + '\n').encode('utf-8'))
        self.count += 1

    def flush_and_fsync(self):
        self.stream.flush()
        os.fsync(self.stream.fileno())
        fd = os.open(self.dir, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def close(self):
        if self.stream is not None and not self.stream.closed:
            try:
                self.flush_and_fsync()
            finally:
                self.stream.close()


def read_docs(dir):
    """Skip corrupt records and keep the first durable copy of each document."""
    seen = set()
    for path in sorted(Path(dir).glob('shard-*.jsonl')):
        with path.open('rb') as stream:
            for line_no, line in enumerate(stream, 1):
                try:
                    doc = json.loads(line.decode('utf-8'))
                    if not isinstance(doc, dict) or not isinstance(doc.get('doc_id'), str):
                        raise ValueError('missing doc_id')
                except (UnicodeError, ValueError):
                    log.warning('Skipping undecodable document at %s:%d', path, line_no)
                    continue
                if doc['doc_id'] not in seen:
                    seen.add(doc['doc_id'])
                    yield doc
