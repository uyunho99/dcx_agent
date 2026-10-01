import importlib
import json
import sqlite3

import pytest

from app.label import questions, rule, route
from app.label.gpt import GptVote
from app.label.jev import JevVote
from app.label.schema import Label, Tags
from app.label.votes import VoteCache


def api():
    return (importlib.import_module('app.label.merge'),
            importlib.import_module('app.label.store'))


def rebuild_final(store, jc, gc):
    count = route.rebuild_final(store, jc, gc)
    route.rebuild_queue(store, jc, gc)
    return count


def votes():
    jev = JevVote(probs={name: .95 if name in ('anchor', 'feel', 'act', 'situation')
                         else .1 for name in rule.GRADE_FIELDS},
                  reason_probs={'ad': .01, 'not_non': .99}, model='offline')
    gpt = GptVote(anchor=True, sem={name: int(name in ('feel', 'act')) for name in rule.SEM},
                  situation=True, signal='workaround')
    return jev, gpt


def caches(tmp_path):
    return VoteCache(tmp_path / 'jev'), VoteCache(tmp_path / 'gpt')


def put(cache, doc_id, vote):
    cache.seed([doc_id])
    cache.put(doc_id, vote.model_dump())


def rows(store, table):
    with sqlite3.connect(store.path) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY doc_id')]


def test_agree_confidence():
    merged = api()[0].merge(*votes())
    assert merged.confidence == pytest.approx(.9)
    assert merged.evidence_level == 'core'
    assert merged.disagree == []
    assert not merged.grade_mismatch
    assert merged.reason_code is None


def test_disagree_takes_jev_and_flags():
    jev, gpt = votes()
    jev.probs['think'] = .5
    merged = api()[0].merge(jev, gpt)
    assert merged.sem['think'] == 1
    assert merged.disagree == ['think']
    assert not merged.grade_mismatch
    assert merged.confidence == pytest.approx(7 / 8 * .5)


def test_grade_mismatch():
    jev, gpt = votes()
    gpt.anchor = False
    merged = api()[0].merge(jev, gpt)
    assert merged.anchor is True
    assert merged.grade_mismatch
    assert merged.evidence_level == 'core'


@pytest.mark.parametrize('signal', ['pain', 'unmet', 'workaround', 'delight', 'none', None])
def test_signal_from_gpt_only(signal):
    jev, gpt = votes()
    gpt.signal = signal
    assert api()[0].merge(jev, gpt).signal == signal


def test_reason_argmax_and_zero_agreement():
    jev, gpt = votes()
    jev.reason_probs = {'not_non': .1, 'ad': .9}
    gpt.reason_code = 'other'
    gpt.anchor = False
    gpt.situation = False
    gpt.sem = {name: 1 - value for name, value in gpt.sem.items()}
    merged = api()[0].merge(jev, gpt)
    assert merged.reason_code == 'ad'
    assert merged.confidence == 0
    assert set(merged.disagree) == {*rule.GRADE_FIELDS, 'reason_code'}


def test_waits_until_both(tmp_path):
    merger, storage = api()
    store = storage.LabelStore(tmp_path / 'v1')
    jc, gc = caches(tmp_path)
    jev, gpt = votes()
    put(jc, 'a', jev)
    put(gc, 'b', gpt)
    assert rebuild_final(store, jc, gc) == 0
    assert rows(store, 'final') == []
    put(gc, 'a', gpt)
    assert rebuild_final(store, jc, gc) == 1
    assert [row['doc_id'] for row in rows(store, 'final')] == ['a']
    label = store.get('a')
    assert isinstance(label, Label)
    assert label.evidence_level == 'core'
    assert label.votes == {'jev': jev.model_dump(), 'gpt': gpt.model_dump()}
    assert store.get('missing') is None


def test_rebuild_is_incremental_and_preserves_queue_status(tmp_path, monkeypatch):
    merger, storage = api()
    store = storage.LabelStore(tmp_path / 'v1')
    jc, gc = caches(tmp_path)
    jev, gpt = votes()
    gpt.anchor = False
    put(jc, 'a', jev)
    put(gc, 'a', gpt)
    assert rebuild_final(store, jc, gc) == 1
    assert rows(store, 'final')[0]['route'] == 'escalated:grade_mismatch'
    assert rows(store, 'queue')[0]['reason'] == 'grade_mismatch'
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE queue SET status='done'")
    calls = []
    original = merger.merge
    def counted(*args):
        calls.append(args)
        return original(*args)
    monkeypatch.setattr(merger, 'merge', counted)
    assert rebuild_final(storage.LabelStore(tmp_path / 'v1'), jc, gc) == 0
    assert calls == []
    put(jc, 'b', jev)
    put(gc, 'b', gpt)
    assert rebuild_final(store, jc, gc) == 1
    assert len(calls) == 1
    assert rows(store, 'queue')[0]['status'] == 'done'


@pytest.mark.parametrize('version', ['rule', 'questions'])
def test_version_change_recomputes_all(tmp_path, monkeypatch, version):
    merger, storage = api()
    store = storage.LabelStore(tmp_path / 'v1')
    jc, gc = caches(tmp_path)
    jev, gpt = votes()
    for doc_id in ('a', 'b'):
        put(jc, doc_id, jev)
        put(gc, doc_id, gpt)
    rebuild_final(store, jc, gc)
    store.submit('a', 'person', 'audit', gpt)
    if version == 'rule':
        monkeypatch.setattr(rule, 'RULE_VERSION', 'r2')
        monkeypatch.setattr(rule, 'grade', lambda tags: 'supporting')
    else:
        monkeypatch.setattr(questions, 'QVER', 'q2')
    assert rebuild_final(store, jc, gc) == 2
    for doc_id in ('a', 'b'):
        label = store.get(doc_id)
        assert label.rule_version == rule.RULE_VERSION
        assert label.questions_version == questions.QVER
        if version == 'rule':
            assert label.evidence_level == 'supporting'
    assert len(rows(store, 'human')) == 1
    assert rebuild_final(store, jc, gc) == 0


def test_bad_vote_queues_without_final(tmp_path):
    merger, storage = api()
    store = storage.LabelStore(tmp_path / 'v1')
    jc, gc = caches(tmp_path)
    jc.seed(['a'])
    jc.mark_bad('a', 'invalid_or_missing_vote')
    put(gc, 'a', votes()[1])
    assert rebuild_final(store, jc, gc) == 0
    assert rows(store, 'final') == []
    assert rows(store, 'queue')[0]['reason'] == 'labeler_failed'
    assert rows(store, 'queue')[0]['status'] == 'open'


def test_submit_is_durable_per_item(tmp_path):
    store = api()[1].LabelStore(tmp_path / 'v1')
    tags = Tags.model_validate(votes()[1].model_dump())
    for mode in ('escalate', 'audit', 'reissue'):
        store.submit('a', 'person', mode, tags)
        saved = rows(api()[1].LabelStore(tmp_path / 'v1'), 'human')
        assert len(saved) == ('escalate', 'audit', 'reissue').index(mode) + 1
        assert saved[-1]['mode'] == mode
        assert json.loads(saved[-1]['tags_json']) == tags.model_dump()
        assert saved[-1]['signal'] == tags.signal
        assert saved[-1]['submitted_at']
    with sqlite3.connect(store.path) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {'final', 'human', 'audit_set', 'queue'} <= tables
    assert 'calib_set' not in tables
    with pytest.raises(ValueError):
        store.submit('a', 'person', 'calibration', tags)
    assert len(rows(store, 'human')) == 3


def test_human_final_survives_rebuild_without_hiding_other_failures(tmp_path, monkeypatch):
    merger, storage = api()
    store = storage.LabelStore(tmp_path / 'v1')
    jc, gc = caches(tmp_path)
    for doc_id in ('human', 'auto'):
        put(jc, doc_id, votes()[0])
        put(gc, doc_id, votes()[1])
    rebuild_final(store, jc, gc)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE final SET source='human', route='audited' WHERE doc_id='human'")
    human_before = store.get('human')
    jc.seed(['bad'])
    jc.mark_bad('bad', 'invalid_or_missing_vote')
    monkeypatch.setattr(rule, 'RULE_VERSION', 'r2')
    assert rebuild_final(store, jc, gc) == 1
    assert store.get('human') == human_before
    assert [row['doc_id'] for row in rows(store, 'queue')] == ['bad']
    assert rebuild_final(store, jc, gc) == 0


def test_failed_recompute_rolls_back_and_never_writes_caches(tmp_path, monkeypatch):
    merger, storage = api()
    store = storage.LabelStore(tmp_path / 'v1')
    jc, gc = caches(tmp_path)
    for doc_id in ('a', 'b'):
        put(jc, doc_id, votes()[0])
        put(gc, doc_id, votes()[1])
    rebuild_final(store, jc, gc)
    before = rows(store, 'final')
    cache_before = [cache.path.read_bytes() for cache in (jc, gc)]
    monkeypatch.setattr(questions, 'QVER', 'q2')
    original = merger.merge
    calls = 0
    def fail_second(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError('interrupted')
        return original(*args)
    monkeypatch.setattr(merger, 'merge', fail_second)
    with pytest.raises(RuntimeError, match='interrupted'):
        rebuild_final(store, jc, gc)
    assert rows(store, 'final') == before
    assert [cache.path.read_bytes() for cache in (jc, gc)] == cache_before


def test_same_grade_disagreement_is_accepted(tmp_path):
    merger, storage = api()
    store = storage.LabelStore(tmp_path / 'v1')
    jc, gc = caches(tmp_path)
    jev, gpt = votes()
    jev.probs['think'] = .5
    put(jc, 'a', jev)
    put(gc, 'a', gpt)
    rebuild_final(store, jc, gc)
    assert store.get('a').route == 'accepted'
    assert rows(store, 'queue') == []
    row = rows(store, 'final')[0]
    assert json.loads(row['disagree_json']) == ['think']
    assert row['grade_mismatch'] == 0
