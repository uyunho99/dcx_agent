"""Overview response contract and audit metrics with a missing Jev vote."""
import pytest

from app.context import store
from app.label import audit
from app.label.overview import overview
from app.label.schema import Tags
from tests.model.test_gpt_only_training import seed_gpt


@pytest.mark.parametrize('mode', ['gpt_only', 'cross'])
def test_overview_labeler_mode_contract(client, data_dir, mode):
    sid, _, labels = seed_gpt(data_dir)
    store.update_session(sid, {'labeling': {'labelerMode': mode}})
    response = client.get(f'/label/{sid}/overview')
    assert response.status_code == 200
    view = response.json()
    assert view['labelerMode'] == mode
    if mode == 'gpt_only':
        assert set(view['progress']) == {'gpt'}
        assert view['mismatchRate'] is None
        assert view['labelerAccuracy']['jev'] is None
    else:
        assert set(view['progress']) == {'jev', 'gpt'}
        assert view['mismatchRate'] == 0
        assert view['labelerAccuracy']['jev']['n'] == 0
    assert overview(sid, sync=False)['labelerMode'] == mode


def test_gpt_only_audit_skips_missing_jev(data_dir):
    sid, _, labels = seed_gpt(data_dir)
    round_id = audit.maybe_new_round(labels, 3, kind='manual')
    label = labels.get('d0')
    tags = Tags(**{key: getattr(label, key) for key in ('anchor', 'sem', 'situation', 'reason_code', 'signal')})
    labels.submit('d0', 'person', 'audit', tags)
    metrics = audit.labeler_accuracy(labels)
    assert metrics['jev']['n'] == 0
    assert metrics['jev']['grade'] == {'n': 0, 'accuracy': None, 'kappa': None}
    assert metrics['gpt']['n'] == 1
    assert metrics['gpt']['grade']['accuracy'] == 1
    assert audit.kappa_ai(labels, round_id)['n'] == 1
    assert overview(sid, sync=False)['labelerAccuracy']['jev'] is None
