"""Offline audit contracts, including persisted sampling and unbiased metrics."""
import importlib
import json

import pytest

from app.config import settings
from app.label import questions, rule
from app.label.schema import Tags
from app.label.store import LabelStore


def api():
    return importlib.import_module('app.label.audit')


def tags(value=1, **changes):
    flat = dict.fromkeys(rule.GRADE_FIELDS, value)
    flat.update(changes)
    return Tags(anchor=bool(flat['anchor']), situation=bool(flat['situation']),
                sem={name: flat[name] for name in rule.SEM}, signal='pain')


def seed(store, count=1000, route='accepted'):
    with store._db() as db:
        for i in range(count):
            truth = tags(i % 2)
            flat = dict(anchor=int(truth.anchor), situation=int(truth.situation), **truth.sem)
            # Balanced errors: Jev relate 80%, outcome 60%; GPT 90%, 70%.
            jev = dict(flat)
            gpt = dict(flat)
            for target, relate_errors, outcome_errors in ((jev, 2, 4), (gpt, 1, 3)):
                if i % 100 < relate_errors * 10:
                    target['relate'] ^= 1
                if i % 100 < outcome_errors * 10:
                    target['outcome'] ^= 1
            votes = {'jev': {'probs': jev}, 'gpt': tags(**gpt).model_dump()}
            db.execute('INSERT INTO final VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (f'd{i:04}', rule.grade(flat), .9, 'agreed', route,
                        truth.model_dump_json(), None, 'pain', rule.RULE_VERSION,
                        questions.QVER, json.dumps(votes), '[]', 0))


def members(store, round):
    with store._db() as db:
        return [r[0] for r in db.execute('SELECT doc_id FROM audit_set WHERE round=? ORDER BY doc_id', (round,))]


def complete(store, round):
    for doc_id in members(store, round):
        store.submit(doc_id, 'alice', 'audit', tags(int(doc_id[1:]) % 2))


def test_first_round_at_1000_then_every_10k(tmp_path):
    audit = api()
    store = LabelStore(tmp_path)
    seed(store)
    assert audit.maybe_new_round(store, 999) is None
    assert audit.maybe_new_round(store, 1000) == 1
    assert audit.maybe_new_round(LabelStore(tmp_path), 1000) is None
    assert audit.maybe_new_round(store, 10000) is None
    assert audit.maybe_new_round(store, 10999) is None
    assert audit.maybe_new_round(store, 11000) == 2
    assert audit.maybe_new_round(store, 20999) is None
    assert audit.maybe_new_round(store, 21000) == 3
    assert all(len(members(store, r)) == 50 for r in (1, 2, 3))


def test_round_samples_accepted_only(tmp_path):
    audit = api()
    stores = [LabelStore(tmp_path / str(i)) for i in range(2)]
    for store in stores:
        seed(store)
        with store._db() as db:
            db.execute("UPDATE final SET route='escalated:grade_mismatch' WHERE doc_id<'d0500'")
        audit.maybe_new_round(store, 1000)
    assert members(stores[0], 1) == members(stores[1], 1)
    assert len(members(stores[0], 1)) == 50
    assert all(doc_id >= 'd0500' for doc_id in members(stores[0], 1))


def test_reissue_two_per_round(tmp_path):
    audit = api()
    store = LabelStore(tmp_path)
    seed(store)
    audit.maybe_new_round(store, 1000)
    assert audit.reissue_items(store, 1) == []
    complete(store, 1)
    audit.maybe_new_round(store, 11000)
    picked = audit.reissue_items(store, 2)
    assert len(picked) == len(set(picked)) == 2
    assert set(picked) <= set(members(store, 1))
    assert not set(picked) & set(members(store, 2))
    assert audit.reissue_items(LabelStore(tmp_path), 2) == picked


def test_self_consistency(tmp_path):
    audit = api()
    store = LabelStore(tmp_path)
    seed(store)
    audit.maybe_new_round(store, 1000)
    ids = members(store, 1)[:2]
    for doc_id in ids:
        store.submit(doc_id, 'alice', 'audit', tags())
    store.submit(ids[0], 'bob', 'reissue', tags(0))  # Different person has no baseline.
    store.submit(ids[0], 'alice', 'reissue', tags())
    store.submit(ids[1], 'alice', 'reissue', tags(outcome=0))
    store.submit('unknown', 'alice', 'reissue', tags())
    result = audit.self_consistency(store)
    assert result['n'] == 2
    assert result['accuracy'] == .5
    assert result['fields']['relate']['accuracy'] == 1
    assert result['fields']['outcome']['accuracy'] == .5


def test_labeler_accuracy_from_audit(tmp_path, monkeypatch):
    audit = api()
    monkeypatch.setattr(settings, 'audit_size', 100)
    store = LabelStore(tmp_path)
    seed(store, 100)
    audit.maybe_new_round(store, 1000)
    complete(store, 1)
    store.submit('d0000', 'alice', 'audit', tags(0))  # Do not double count.
    store.submit('d0001', 'alice', 'reissue', tags(0))  # Not audit truth.
    result = audit.labeler_accuracy(store)
    for labeler, expected in [('jev', (.8, .6)), ('gpt', (.9, .7))]:
        assert result[labeler]['n'] == 100
        for field, accuracy in zip(('relate', 'outcome'), expected):
            metric = result[labeler]['fields'][field]
            assert metric['n'] == 100
            assert metric['accuracy'] == pytest.approx(accuracy)
            assert metric['kappa'] == pytest.approx(2 * accuracy - 1)
        assert result[labeler]['fields']['anchor']['accuracy'] == 1


@pytest.mark.parametrize('history, needed', [
    ([], False), ([.9, .7], False), ([.9, .8, .7], True),
    ([.9, .8, .75], False), ([.9, .7, .7], False),
    ([.7, .8, .6], False), ([.9, None, .7], False),
    ([.95, .9, .8, .7], True),
])
def test_definition_signal(history, needed):
    result = api().definition_signal([{'grade': {'kappa': k}} for k in history])
    assert result['needed'] is needed
    assert bool(result['reason']) is needed


def test_audit_override_sets_human(tmp_path):
    audit = api()
    store = LabelStore(tmp_path)
    seed(store)
    audit.maybe_new_round(store, 1000)
    doc_id = members(store, 1)[0]
    original = store.get(doc_id)
    correction = tags(1 - int(original.anchor))
    store.submit(doc_id, 'alice', 'audit', correction)
    result = audit.kappa_ai(store, 1)
    assert result['n'] == 1
    assert result['grade']['accuracy'] == 0
    updated = LabelStore(tmp_path).get(doc_id)
    assert updated.source == 'human'
    assert updated.evidence_level != original.evidence_level
    assert updated.sem == correction.sem
    assert updated.votes == original.votes
    assert audit.kappa_ai(store, 1) == result  # Snapshot survives correction/restart.
    assert audit.apply_audit_overrides(store) == 0


def test_empty_and_degenerate_metrics(tmp_path):
    audit = api()
    store = LabelStore(tmp_path)
    assert audit.kappa_ai(store, 1)['grade'] == {'n': 0, 'accuracy': None, 'kappa': None}
    assert audit.labeler_accuracy(store)['jev']['n'] == 0
    assert audit.self_consistency(store)['n'] == 0
    assert audit.maybe_new_round(store, 1000) is None
    seed(store, 1)
    audit.maybe_new_round(store, 1000)
    complete(store, 1)
    metric = audit.kappa_ai(store, 1)['grade']
    assert metric == {'n': 1, 'accuracy': 1.0, 'kappa': None}


def test_repeated_round_uses_new_judgment(tmp_path, monkeypatch):
    audit = api()
    monkeypatch.setattr(settings, 'audit_size', 1)
    monkeypatch.setattr(settings, 'audit_reissue', 0)
    store = LabelStore(tmp_path)
    seed(store, 1)
    audit.maybe_new_round(store, 1000)
    complete(store, 1)
    first = audit.kappa_ai(store, 1)
    audit.maybe_new_round(store, 11000)
    assert audit.kappa_ai(store, 2)['n'] == 0
    store.submit('d0000', 'alice', 'audit', tags())
    assert audit.kappa_ai(store, 2)['grade']['accuracy'] == 0
    assert audit.kappa_ai(store, 1) == first


def test_override_ignores_unselected_and_other_modes(tmp_path):
    audit = api()
    store = LabelStore(tmp_path)
    seed(store, 2)
    store.submit('d0000', 'alice', 'audit', tags())
    store.submit('d0001', 'alice', 'escalate', tags(0))
    assert audit.apply_audit_overrides(store) == 0
    assert store.get('d0000').source == 'agreed'


def test_kappa_ai_balanced_errors_and_stored_grade(tmp_path, monkeypatch):
    audit = api()
    monkeypatch.setattr(settings, 'audit_size', 100)
    store = LabelStore(tmp_path)
    seed(store, 100)
    audit.maybe_new_round(store, 1000)
    for i in range(100):
        value = i % 2
        store.submit(f'd{i:04}', 'alice', 'audit', tags(1 - value if i < 20 else value))
    result = audit.kappa_ai(store, 1)
    assert result['n'] == 100
    for metric in [result['grade'], *result['fields'].values()]:
        assert metric['accuracy'] == pytest.approx(.8)
        assert metric['kappa'] == pytest.approx(.6)
    # The historical AI grade is the recorded grade, not a newly applied rule.
    monkeypatch.setattr(rule, 'grade', lambda _: 'core')
    assert audit.kappa_ai(store, 1)['grade']['accuracy'] == .5


def test_settings_control_schedule_and_sample(tmp_path, monkeypatch):
    audit = api()
    for key, value in [('audit_first', 3), ('audit_every', 4), ('audit_size', 3), ('audit_reissue', 1)]:
        monkeypatch.setattr(settings, key, value)
    store = LabelStore(tmp_path)
    seed(store, 10)
    assert audit.maybe_new_round(store, 2) is None
    assert audit.maybe_new_round(store, 3) == 1
    complete(store, 1)
    assert audit.maybe_new_round(store, 6) is None
    assert audit.maybe_new_round(store, 7) == 2
    assert len(members(store, 2)) == 3
    assert len(audit.reissue_items(store, 2)) == 1


def test_provider_payloads_from_vote_cache(tmp_path):
    from app.label.gpt import GptVote
    from app.label.jev import JevVote
    from app.label.route import rebuild_final
    from app.label.votes import VoteCache

    audit = api()
    store = LabelStore(tmp_path / 'v1')
    truth = tags()
    jev = JevVote(probs=dict.fromkeys(rule.GRADE_FIELDS, .5),
                  reason_probs={'not_non': 1.0}, model='offline')
    gpt = GptVote(**truth.model_dump())
    caches = [VoteCache(tmp_path / name) for name in ('jev', 'gpt')]
    for cache, vote in zip(caches, (jev, gpt)):
        cache.seed(['document'])
        cache.put('document', vote.model_dump())
    assert rebuild_final(store, *caches) == 1
    audit.maybe_new_round(store, 1000)
    store.submit('document', 'alice', 'audit', truth)
    for summary in audit.labeler_accuracy(store).values():
        assert summary['n'] == 1
        assert all(metric['accuracy'] == 1 for metric in summary['fields'].values())
