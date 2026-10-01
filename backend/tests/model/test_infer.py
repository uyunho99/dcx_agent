import numpy as np
import pytest

from app.model import infer, registry
from app.label import rule
from .test_registry import save_model


def test_rule_change_no_retrain(data_dir, monkeypatch):
    model = registry.load(save_model())
    pred = infer.predict(model, np.zeros((1, 1032)))[0]
    assert pred.level == 'core' and pred.relevanceScore > .8
    monkeypatch.setattr(rule, 'grade_probs', lambda tags: dict(core=0., supporting=1., non=0.))
    changed = infer.from_tag_probs(pred.tagProbs, pred.memberTagProbs)
    assert changed.level == 'supporting'
    assert changed.relevanceScore == 1 and changed.predEntropy == 0
    assert changed.tagProbs == pred.tagProbs


def test_infer_does_not_rebuild_members(data_dir, monkeypatch):
    model = registry.load(save_model())
    def forbidden(*args, **kwargs):
        pytest.fail('inference must reuse loaded members')
    monkeypatch.setattr('app.model.net.MultiHeadMLP.__init__', forbidden)
    for _ in range(2):
        pred = infer.predict(model, np.zeros((2, 1032)))
        assert len(pred) == 2
        assert pred[0].confidence == pytest.approx(max(pred[0].gradeProbs.values()))
        assert pred[0].memberDisagree is False


@pytest.mark.parametrize('p,disagree,expected', [(.1, False, 'accepted'), (.9, False, 'accepted'),
    (.2, False, 'model_uncertain'), (.8, False, 'model_uncertain'), (.9, True, 'model_disagree')])
def test_model_routing_cuts(p, disagree, expected):
    from types import SimpleNamespace
    assert infer.route_prediction(SimpleNamespace(relevanceScore=p, memberDisagree=disagree)) == expected


def test_saved_rule_change_does_not_invoke_model(client, data_dir, monkeypatch):
    from .test_model_mode import prepared, context
    from app.context import store
    from app.config import settings
    from app.label.overview import labels_for
    sid, _ = prepared(data_dir)
    model_id = save_model()
    store.update_session(sid, {'labeling': {'mode': 'model', 'modelId': model_id}})
    monkeypatch.setattr(settings, 'monitor_rate', 0)
    infer.run_worker(context(sid))
    monkeypatch.setattr(rule, 'RULE_VERSION', 'r2')
    monkeypatch.setattr(rule, 'grade_probs', lambda p: dict(core=0., supporting=1., non=0.))
    monkeypatch.setattr(infer, 'predict', lambda *args: pytest.fail('rule change must not rerun model'))
    view = client.get(f'/label/{sid}/overview').json()
    assert view['levelDistribution']['supporting'] == 3
    assert labels_for(sid, store.load_session(sid)).get('d0').rule_version == 'r2'
    assert client.post(f'/train/{sid}/export', json={}).json()['relevant'] == 3
