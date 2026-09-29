from concurrent.futures import ThreadPoolExecutor
import pytest
from app.context import store


def test_concurrent_session_patches_both_survive(data_dir):
    def write(patch):
        for _ in range(50):
            store.update_session('s1', patch)
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(write, [{'a': 1}, {'b': 2}]))
    assert store.load_session('s1') == {'a': 1, 'b': 2}


def test_atomic_write_no_partial(data_dir, monkeypatch):
    store.update_session('s1', {'a': 1})
    def fail(*args):
        raise OSError('disk failure')
    monkeypatch.setattr(store.os, 'replace', fail)
    with pytest.raises(OSError):
        store.update_session('s1', {'a': 2})
    assert store.load_session('s1') == {'a': 1}
