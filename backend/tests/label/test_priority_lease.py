from app.label.votes import VoteCache


def test_priority_documents_are_leased_first(tmp_path):
    cache = VoteCache(tmp_path)
    cache.seed(['a', 'b', 'c', 'd'], {'a': 1, 'b': 1, 'c': 0, 'd': 0})
    assert cache.lease(2, 'r1') == ['c', 'd']
    assert cache.lease(2, 'r1') == ['a', 'b']


def test_seed_without_priorities_keeps_id_order(tmp_path):
    cache = VoteCache(tmp_path)
    cache.seed(['b', 'a'])
    assert cache.lease(2, 'r1') == ['a', 'b']
