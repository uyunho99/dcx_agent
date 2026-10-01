"""Source indexing commits bounded batches and safely retries incomplete files."""
from contextlib import contextmanager
import json
import sqlite3

import pytest

from app.label.overview import index_documents
from app.label.store import LabelStore


def corpus(data_dir, count=20003):
    root = data_dir / 'derived/s/c1/p_123456789abc/docs'
    root.mkdir(parents=True)
    path = root / 'part.jsonl'
    docs = [dict(doc_id=str(i), text=f'text {i}', secret='hidden',
                 comments=[{'text': 'comment', 'secret': 'hidden'}]) for i in range(count)]
    path.write_text('\n'.join(map(json.dumps, docs)) + '\n')
    return path, {'prep': {'derivedRef': {'collectionId': 'c1', 'prepKey': 'p_123456789abc'}}}


def test_index_releases_writer_between_batches(data_dir, monkeypatch):
    path, data = corpus(data_dir)
    labels = LabelStore(data_dir / 'labels')
    original = labels._db
    committed = []
    @contextmanager
    def observed():
        with original() as db:
            before = db.total_changes
            yield db
            inserted = db.total_changes - before
        # A separate writer can acquire the database after every transaction.
        with sqlite3.connect(labels.path, timeout=0) as other:
            other.execute('BEGIN IMMEDIATE')
        committed.append(inserted)
    monkeypatch.setattr(labels, '_db', observed)
    index_documents('s', data, labels)
    assert max(committed) <= 10001
    assert sum(n > 0 for n in committed) >= 3
    with original() as db:
        rows = {r[0]: json.loads(r[1]) for r in db.execute('SELECT * FROM documents')}
        assert len(rows) == 20003
        assert rows['20002'] == {'doc_id': '20002', 'text': 'text 20002', 'comments': [{'text': 'comment'}]}
        assert db.execute('SELECT stamp FROM document_files WHERE path=?', (str(path),)).fetchone()
    committed.clear()
    index_documents('s', data, labels)
    assert sum(committed) == 0


def test_incomplete_index_is_not_stamped_and_can_retry(data_dir):
    path, data = corpus(data_dir, 10003)
    valid = path.read_text()
    path.write_text(valid + '{bad json\n')
    labels = LabelStore(data_dir / 'labels')
    with pytest.raises(json.JSONDecodeError):
        index_documents('s', data, labels)
    with labels._db() as db:
        assert db.execute('SELECT count(*) FROM document_files').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM documents').fetchone()[0] == 10000
    path.write_text(valid)
    index_documents('s', data, labels)
    with labels._db() as db:
        assert db.execute('SELECT count(*) FROM documents').fetchone()[0] == 10003
        assert db.execute('SELECT count(*) FROM document_files').fetchone()[0] == 1
