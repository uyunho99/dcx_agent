"""Follow-up regressions for the cached overview training count."""
import json
import shutil

import numpy as np
import pytest

from app.context import store
from app.label import rule
from app.label.overview import labels_for, overview
from app.model import infer
from app.vectors.store import VectorStore
from tests.model.test_export import seed
from tests.model.test_model_mode import prepared


@pytest.fixture
def counted(data_dir, monkeypatch):
    sid, docs = prepared(data_dir, 4)
    seed(sid)
    calls = dict(documents=0, vectors=0)
    documents, shards = infer.documents, VectorStore.iter_shards

    def read_documents(*args, **kwargs):
        calls['documents'] += 1
        return documents(*args, **kwargs)

    def read_vectors(*args, **kwargs):
        calls['vectors'] += 1
        yield from shards(*args, **kwargs)

    monkeypatch.setattr(infer, 'documents', read_documents)
    monkeypatch.setattr(VectorStore, 'iter_shards', read_vectors)
    return sid, docs, calls


def test_overview_reuses_count_and_human_submit_invalidates(client, counted):
    sid, _, calls = counted
    url = f'/label/{sid}/overview'
    assert client.get(url).json()['trainable'] == 3
    assert calls == dict(documents=1, vectors=1)
    assert client.get(url).json()['trainable'] == 3
    assert calls == dict(documents=1, vectors=1)
    labels = labels_for(sid, store.load_session(sid))
    with labels._db() as db:
        db.execute("INSERT INTO queue VALUES ('d3','model_uncertain',1,'open')")
    tags = dict(anchor=True, situation=True, sem=dict.fromkeys(rule.SEM, 1))
    response = client.post(f'/label/{sid}/submit', json=dict(
        doc_id='d3', labeler='person', mode='escalate', tags=tags))
    assert response.status_code == 200, response.text
    assert client.get(url).json()['trainable'] == 4
    assert calls == dict(documents=2, vectors=2)
    assert client.get(url).json()['trainable'] == 4
    assert calls == dict(documents=2, vectors=2)


@pytest.mark.parametrize('change,expected', [
    ('final_update', 2), ('final_delete', 2), ('human', 3),
    ('documents', 2), ('manifest', 3), ('vectors', 2),
    ('vector_index', 2), ('derived_ref', 2),
])
def test_count_invalidates_on_input_changes(counted, change, expected):
    sid, docs, calls = counted
    assert overview(sid)['trainable'] == 3
    assert overview(sid)['trainable'] == 3
    assert calls == dict(documents=1, vectors=1)
    data = store.load_session(sid)
    root = infer.prepared_root(sid, data)
    labels = labels_for(sid, data)
    if change == 'final_update':
        with labels._db() as db:
            db.execute("UPDATE final SET source='model',route='accepted' WHERE doc_id='d0'")
    elif change == 'final_delete':
        with labels._db() as db:
            db.execute("DELETE FROM final WHERE doc_id='d0'")
    elif change == 'human':
        labels.submit('d0', 'person', 'escalate', dict(
            anchor=True, situation=True, sem=dict.fromkeys(rule.SEM, 1)))
    elif change == 'documents':
        (root / 'docs/part.jsonl').write_text('\n'.join(map(json.dumps, docs[1:])))
    elif change == 'manifest':
        manifest = store.read_json(root / 'manifest.json')
        store.write_json(root / 'manifest.json', {**manifest, 'revision': 2})
    elif change == 'vectors':
        # Same row count and file size; only a shard stamp changes.
        shard = next((root / 'vectors').glob('shard-*.f16'))
        matrix = np.ones((4, 1024), dtype=np.float16)
        matrix[0] = 0
        shard.write_bytes(matrix.tobytes())
    elif change == 'vector_index':
        index = root / 'vectors/ids.jsonl'
        index.write_text(index.read_text().replace('"d0"', '"missing"'))
    elif change == 'derived_ref':
        replacement = root.with_name('p_abcdef123456')
        shutil.copytree(root, replacement)
        (replacement / 'docs/part.jsonl').write_text('\n'.join(map(json.dumps, docs[1:])))
        store.update_session(sid, {'prep': {'derivedRef': {
            'collectionId': 'c1', 'prepKey': replacement.name}}})
    assert overview(sid)['trainable'] == expected
    assert calls == dict(documents=2, vectors=2)
    assert overview(sid)['trainable'] == expected
    assert calls == dict(documents=2, vectors=2)


def test_empty_selection_is_cached_and_new_labels_invalidate(counted):
    sid, _, calls = counted
    labels = labels_for(sid, store.load_session(sid))
    with labels._db() as db:
        db.execute('DELETE FROM final')
    assert overview(sid)['trainable'] == 0
    assert overview(sid)['trainable'] == 0
    assert calls == dict(documents=0, vectors=0)
    seed(sid)
    assert overview(sid)['trainable'] == 3
    assert overview(sid)['trainable'] == 3
    assert calls == dict(documents=1, vectors=1)


def test_label_change_during_scan_is_not_cached_as_current(counted, monkeypatch):
    sid, _, calls = counted
    labels = labels_for(sid, store.load_session(sid))
    documents = infer.documents

    def change_during_read(*args, **kwargs):
        with labels._db() as db:
            db.execute("DELETE FROM final WHERE doc_id='d0'")
        return documents(*args, **kwargs)

    monkeypatch.setattr(infer, 'documents', change_during_read)
    assert overview(sid)['trainable'] == 3
    monkeypatch.setattr(infer, 'documents', documents)
    assert overview(sid)['trainable'] == 2
    assert overview(sid)['trainable'] == 2
    assert calls == dict(documents=2, vectors=2)
