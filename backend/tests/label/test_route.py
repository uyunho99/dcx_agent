import importlib

from app.label.store import LabelStore
from app.label.votes import VoteCache
from app.label import rule, questions
from app.label.schema import Tags


def tags(value=1):
    return Tags(anchor=bool(value), situation=bool(value), sem=dict.fromkeys(rule.SEM, value))


def test_route_order():
    route = importlib.import_module('app.label.route').route
    assert route({'labeler_failed': True, 'grade_mismatch': True}) == 'labeler_failed'
    assert route({'grade_mismatch': True}) == 'grade_mismatch'
    assert route({'confidence': 0, 'disagree': ['anchor']}) == 'accepted'


def test_failed_doc_reaches_queue(tmp_path):
    api = importlib.import_module('app.label.route')
    store = LabelStore(tmp_path / 'v1')
    caches = [VoteCache(tmp_path / name) for name in ('jev', 'gpt')]
    for cache in caches:
        cache.seed(['failed'])
    for _ in range(3):
        caches[0].fail('failed', 'invalid')
    api.rebuild_queue(store, *caches)
    assert api.next_item(store)['reason'] == 'labeler_failed'
    api.submit_item(store, 'failed', 'alice', 'escalate', tags())
    assert LabelStore(tmp_path / 'v1').get('failed').source == 'human'
    assert api.next_item(store) is None
    api.rebuild_queue(store, *caches)
    assert api.next_item(store) is None


def test_recovered_failure_closes_queue(tmp_path):
    api = importlib.import_module('app.label.route')
    store = LabelStore(tmp_path)
    with store._db() as db:
        db.execute("INSERT INTO queue VALUES ('d', 'labeler_failed', 0, 'open')")
        db.execute('INSERT INTO final VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   ('d', 'core', .9, 'agreed', 'accepted', tags().model_dump_json(),
                    None, None, rule.RULE_VERSION, questions.QVER, '{}', '[]', 0))
    api.rebuild_queue(store)
    assert api.next_item(store) is None


def test_incremental_pairs_restart_rule_change_and_human(tmp_path, monkeypatch):
    from tests.label.test_merge import votes, put
    from app.label import merge
    api = importlib.import_module('app.label.route')
    labels = LabelStore(tmp_path / 'v1')
    jc, gc = [VoteCache(tmp_path / name) for name in ('jev', 'gpt')]
    j, g = votes()
    put(jc, 'a', j)
    api.rebuild_queue(labels, jc, gc)
    put(gc, 'a', g)
    api.rebuild_queue(labels, jc, gc)
    assert labels.get('a') is not None
    calls = []
    original = merge.merge
    monkeypatch.setattr(merge, 'merge', lambda *a: calls.append(1) or original(*a))
    api.rebuild_queue(LabelStore(tmp_path / 'v1'), jc, gc)
    assert calls == []
    put(gc, 'b', g)
    api.rebuild_queue(labels, jc, gc)
    put(jc, 'b', j)
    api.rebuild_queue(labels, jc, gc)
    assert len(calls) == 1
    with labels._db() as db:
        db.execute("UPDATE final SET source='human' WHERE doc_id='a'")
    monkeypatch.setattr(rule, 'RULE_VERSION', 'future-rule')
    api.rebuild_queue(labels, jc, gc)
    assert len(calls) == 2
    assert labels.get('a').source == 'human'
    assert labels.get('b').rule_version == 'future-rule'
    # A new version catches up all shared cache results with independent cursors.
    new = LabelStore(tmp_path / 'v2')
    api.rebuild_queue(new, jc, gc)
    assert new.get('a') and new.get('b')


def test_initial_incremental_sync_invalidates_old_rule(tmp_path, monkeypatch):
    from tests.label.test_merge import votes, put
    from app.label.merge import rebuild_final
    api = importlib.import_module('app.label.route')
    labels = LabelStore(tmp_path / 'v1')
    jc, gc = [VoteCache(tmp_path / name) for name in ('jev', 'gpt')]
    for cache, vote in zip((jc, gc), votes()):
        put(cache, 'd', vote)
    rebuild_final(labels, jc, gc)
    monkeypatch.setattr(rule, 'RULE_VERSION', 'future-rule')
    api.rebuild_queue(labels, jc, gc)
    assert labels.get('d').rule_version == 'future-rule'


def test_schema_backfill_once_and_queue_unchanged(tmp_path):
    from tests.label.test_merge import votes, put
    api = importlib.import_module('app.label.route')
    labels = LabelStore(tmp_path / 'v1')
    jc, gc = [VoteCache(tmp_path / name) for name in ('jev', 'gpt')]
    j, g = votes()
    g.anchor = False
    put(jc, 'd', j)
    put(gc, 'd', g)
    api.rebuild_queue(labels, jc, gc)
    with labels._db() as db:
        db.execute("CREATE TRIGGER reject_backfill BEFORE INSERT ON label_events BEGIN SELECT RAISE(ABORT, 'repeated backfill'); END")
        db.execute("CREATE TRIGGER reject_update BEFORE UPDATE ON queue BEGIN SELECT RAISE(ABORT, 'unchanged queue update'); END")
    api.rebuild_queue(LabelStore(tmp_path / 'v1'), jc, gc)
    assert api.next_item(labels)['doc_id'] == 'd'
