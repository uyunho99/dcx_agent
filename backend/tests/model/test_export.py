import json

import pytest

from app.context import store
from app.label import rule, questions
from app.label.overview import labels_for
from app.model import export
from .test_model_mode import prepared


def seed(sid):
    labels = labels_for(sid, store.load_session(sid))
    with labels._db() as db:
        for i, level in enumerate(['core', 'supporting', 'non']):
            tags = dict(anchor=i != 2, situation=i == 0, sem={k: int(i == 0 or k == 'sense') for k in rule.SEM})
            db.execute('INSERT INTO final VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (f'd{i}', level, .87, 'human', 'escalated:human', json.dumps(tags), None, 'pain',
                 rule.RULE_VERSION, questions.QVER, '{}', '[]', 0))


def test_export_relevant_contract(client, data_dir):
    sid, _ = prepared(data_dir)
    seed(sid)
    response = client.post(f'/train/{sid}/export', json={'withoutModel': True})
    assert response.status_code == 200, response.text
    ref = store.load_session(sid)['training']['exportRef']
    assert ref.startswith(f'classified/{sid}/v1/gen-') and ref.endswith('/relevant.jsonl')
    rows = [json.loads(line) for line in (data_dir / ref).read_text().splitlines()]
    assert [r['evidence_level_pred'] for r in rows] == ['core', 'supporting']
    assert len((data_dir / ref).with_name('all.jsonl').read_text().splitlines()) == 3
    required = {'doc_id', 'title', 'desc', 'cafe', 'kw', 'evidence_level_pred', 'confidence',
        'pred_entropy', 'relevance_score', 'tagProbs', 'signal', 'source'}
    assert required <= rows[0].keys()
    assert rows[0]['desc'] == 'body text' and rows[0]['confidence'] == .87


def test_export_without_model(client, data_dir):
    sid, _ = prepared(data_dir)
    seed(sid)
    response = client.post(f'/train/{sid}/export', json={'withoutModel': True})
    assert response.status_code == 200
    stage = json.loads((store.session_dir(sid) / 'stage_5.json').read_text())
    assert stage['model'] is None and stage['monitorDivergence'] is None
    assert stage['levelDistribution'] == dict(core=1/3, supporting=1/3, non=1/3)


@pytest.mark.parametrize('unavailable', ['zero', 'missing', 'head'])
@pytest.mark.parametrize('source,route', [('agreed', 'accepted'), ('human', 'audited')])
def test_llm_export_unavailable_prediction_uses_final(client, data_dir, unavailable, source, route):
    import numpy as np
    from app.model import infer, registry
    from app.vectors.store import VectorStore
    from .test_model_mode import context
    from .test_registry import save_model
    sid, _ = prepared(data_dir)
    seed(sid)
    labels = labels_for(sid, store.load_session(sid))
    with labels._db() as db:
        db.execute('UPDATE final SET source=?,route=?', (source, route))
    mid = save_model()
    root = data_dir / f'derived/{sid}/c1/p_123456789abc'
    if unavailable in ('zero', 'missing'):
        import shutil
        # Replace vector artifacts without changing the prepared documents.
        for path in root.iterdir():
            if path.name not in ('docs', 'manifest.json'):
                shutil.rmtree(path) if path.is_dir() else path.unlink()
        if unavailable == 'zero':
            vectors = np.ones((3, 1024))
            vectors[0] = 0
            VectorStore(root).write_shard(['d0', 'd1', 'd2'], vectors, [True, False, False])
    else:
        path = data_dir / 'models' / mid / 'meta.json'
        meta = registry.metadata(mid)
        meta['perHead']['anchor'] = {'trained': False}
        store.write_json(path, meta)
    store.update_session(sid, {'labeling': {'mode': 'llm'}, 'training': {'modelId': mid}})
    infer.run_worker(context(sid))
    with labels._db() as db:
        assert db.execute("SELECT invalid_vector FROM model_predictions WHERE doc_id='d0'").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM queue WHERE status='open'").fetchone()[0] == 0
    result = export.write(sid)
    rows = [json.loads(line) for line in (data_dir / result['allRef']).read_text().splitlines()]
    row = next(r for r in rows if r['doc_id'] == 'd0')
    assert row['evidence_level_pred'] == 'core' and row['source'] == source
    assert row['confidence'] == .87
    assert row['prediction'] == 'unavailable'
    assert all(row[key] is None for key in ('modelId', 'tagProbs', 'pred_entropy', 'relevance_score'))
    with labels._db() as db:
        db.execute("DELETE FROM final WHERE doc_id='d0'")
    with pytest.raises(store.StoreError):
        export.write(sid)
