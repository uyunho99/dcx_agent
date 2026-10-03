"""GPT-only training selection and nullable export regression coverage."""
import json

from app.context import store
from app.label import route
from app.label.overview import caches_for, labels_for
from app.model import dataset, export
from app.model.train import build_targets
from .test_model_mode import prepared
from .test_train import row


def gpt_row(i=0, **kwargs):
    result = row(i, source='gpt_only', **kwargs)
    result['votes_json'] = json.dumps({'jev': None, 'gpt': json.loads(result['tags_json'])})
    return result


def seed_gpt(data_dir):
    sid, docs = prepared(data_dir)
    store.update_session(sid, {'labeling': {'started': True, 'labelerMode': 'gpt_only'}})
    data = store.load_session(sid)
    labels = labels_for(sid, data)
    cache = caches_for(sid, data)['gpt']
    cache.seed([doc['doc_id'] for doc in docs])
    for i, doc in enumerate(docs):
        cache.put(doc['doc_id'], json.loads(gpt_row(i, anchor=i != 2)['tags_json']))
    route.sync(labels, None, cache, mode='gpt_only')
    return sid, data, labels


def test_gpt_only_targets_use_gpt_binary_and_reason_one_hot():
    rows = [gpt_row(), gpt_row(1, anchor=False),
            dict(gpt_row(2), route='escalated:grade_mismatch'),
            dict(gpt_row(3), route='audited'), row(4), row(5, source='agreed'),
            dict(row(6, source='agreed'), route='audited'), row(7, source='model')]
    targets = build_targets(rows)
    assert targets.doc_ids.tolist() == ['0', '1', '4', '5']
    for i in range(2):
        gpt = json.loads(rows[i]['votes_json'])['gpt']
        assert targets.values['anchor'][i].tolist() == [int(gpt['anchor'])]
        assert targets.values['sem'][i].tolist() == list(gpt['sem'].values())
        assert targets.values['situation'][i].tolist() == [int(gpt['situation'])]
    assert targets.values['reason'][1].tolist() == [0, 0, 0, 1]
    assert targets.masks['reason'].tolist() == [False, True, False, False]
    assert targets.weights.tolist() == [1, 1, 3, 1]


def test_trainable_count_includes_accepted_gpt_only(data_dir):
    sid, data, labels = seed_gpt(data_dir)
    assert len(dataset.training_rows(labels)) == 3
    assert dataset.trainable_count(sid, data, labels) == 3
    assert dataset.trainable_count(sid, data, labels) == 3  # cached
    with labels._db() as db:
        db.execute("UPDATE final SET route='audited' WHERE doc_id='d0'")
    assert dataset.trainable_count(sid, data, labels) == 2
    with labels._db() as db:
        db.execute("UPDATE final SET source='human' WHERE doc_id='d0'")
    assert dataset.trainable_count(sid, data, labels) == 3


def test_export_preserves_null_confidence_and_zero_entropy(data_dir):
    sid, _, _ = seed_gpt(data_dir)
    result = export.write(sid, without_model=True)
    for ref in ('allRef', 'exportRef'):
        rows = [json.loads(line) for line in (data_dir / result[ref]).read_text().splitlines()]
        assert rows
        assert all(r['source'] == 'gpt_only' and r['confidence'] is None and r['pred_entropy'] == 0 for r in rows)
    stage = json.loads((store.session_dir(sid) / 'stage_5.json').read_text())
    assert stage['mismatchRate'] is None
    assert stage['labelerAccuracy']['jev'] is None
    assert stage['agreementRate'] is None
    assert all(value is None for value in stage['kappaLabelers'].values())
