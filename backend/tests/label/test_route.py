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
