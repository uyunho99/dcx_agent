import json
import math

import pytest

from app.config import settings
from app.context import store
from app.label import questions, rule
from app.label.overview import labels_for
from app.model import export, infer
from .test_model_mode import context, prepared
from .test_registry import save_model


def export_label(data_dir, jev_probs, gpt_tags, *, source='agreed', route='accepted'):
    sid, _ = prepared(data_dir, n=1)
    tags = dict(anchor=True, situation=True,
                sem={name: int(name in ('sense', 'feel')) for name in rule.SEM})
    votes = {'gpt': gpt_tags}
    if jev_probs is not None:
        votes['jev'] = dict(probs=jev_probs, reason_probs={'not_non': 1.}, model='fake')
    labels = labels_for(sid, store.load_session(sid))
    with labels._db() as db:
        db.execute('INSERT INTO final VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   ('d0', 'core', .87, source, route, json.dumps(tags), None, 'pain',
                    rule.RULE_VERSION, questions.QVER, json.dumps(votes), '[]', 0))
    result = export.write(sid, without_model=True)
    row = json.loads((data_dir / result['allRef']).read_text())
    assert row['tagProbs'] == dict(anchor=1., situation=1.,
                                  **{k: float(v) for k, v in tags['sem'].items()})
    assert row['evidence_level_pred'] == 'core'
    assert row['confidence'] == .87 and row['relevance_score'] == 1.
    assert json.loads((data_dir / result['exportRef']).read_text()) == row
    return row


def core_votes():
    probs = {name: float(name in ('anchor', 'situation', 'sense', 'feel'))
             for name in rule.GRADE_FIELDS}
    tags = dict(anchor=True, situation=True,
                sem={name: int(probs[name]) for name in rule.SEM})
    return probs, tags


@pytest.mark.parametrize('field', ['anchor', 'situation', 'sense', 'feel'])
@pytest.mark.parametrize('route', ['accepted', 'audited'])
def test_label_disagreement_entropy(data_dir, field, route):
    probs, gpt = core_votes()
    if field in rule.SEM:
        gpt['sem'][field] = 0
    else:
        gpt[field] = False
    row = export_label(data_dir, probs, gpt, route=route)
    # One decisive tag is 0.5: core/other grade masses are each 0.5.
    assert row['pred_entropy'] == pytest.approx(math.log(2))


@pytest.mark.parametrize('anchor', [1., .999, .8])
def test_label_agreement_entropy_uses_jev_probability(data_dir, anchor):
    probs, gpt = core_votes()
    probs['anchor'] = anchor
    row = export_label(data_dir, probs, gpt)
    # Only anchor is uncertain: core=(anchor+1)/2, non=1-core.
    core = (anchor + 1.) / 2
    expected = -core * math.log(core)
    if core < 1:
        expected -= (1 - core) * math.log(1 - core)
    assert row['pred_entropy'] == pytest.approx(expected)


def test_label_without_jev_has_zero_entropy(data_dir):
    _, gpt = core_votes()
    assert export_label(data_dir, None, gpt)['pred_entropy'] == 0.


def test_human_label_ignores_disagreeing_votes(data_dir):
    probs, gpt = core_votes()
    gpt['anchor'] = False
    assert export_label(data_dir, probs, gpt, source='human')['pred_entropy'] == 0.


def test_model_export_preserves_prediction_entropy(data_dir, monkeypatch):
    sid, _ = prepared(data_dir, n=1)
    mid = save_model()
    store.update_session(sid, {'labeling': {'mode': 'model', 'modelId': mid}})
    monkeypatch.setattr(settings, 'monitor_rate', 0)
    infer.run_worker(context(sid))
    labels = labels_for(sid, store.load_session(sid))
    with labels._db() as db:
        pred = json.loads(db.execute('SELECT payload FROM model_predictions').fetchone()[0])
    assert pred['predEntropy'] > 0
    result = export.write(sid)
    row = json.loads((data_dir / result['allRef']).read_text())
    assert row['source'] == 'model'
    assert row['pred_entropy'] == pred['predEntropy']
    assert row['tagProbs'] == pred['tagProbs']
