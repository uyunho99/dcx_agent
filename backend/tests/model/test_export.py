import json

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
    assert ref == f'classified/{sid}/v1/relevant.jsonl'
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
