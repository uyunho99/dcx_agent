from concurrent.futures import ThreadPoolExecutor
import pytest
from app.context import store


def _concurrent_patches(sid):
    def write(prefix):
        for i in range(50):
            store.update_session(sid, {f'{prefix}{i}': i})
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(write, ['a', 'b']))
    saved = store.load_session(sid)
    assert {key: saved.get(key) for key in expected_keys()} == expected_keys()


def expected_keys():
    return {f'{prefix}{i}': i for prefix in ['a', 'b'] for i in range(50)}


def test_concurrent_session_patches_both_survive(data_dir):
    store.update_session('s1', {})
    _concurrent_patches('s1')


def test_concurrent_v2_session_patches_both_survive(client):
    from test_api import create
    sid = create(client)
    root = store.root_dir(sid)
    assert store.read_json(root / 'meta.json')['activeVersion'] == 'v1'
    assert (root / 'active').resolve() == store.session_dir(sid)
    assert (root / 'session.json').is_symlink()
    _concurrent_patches(sid)


def test_atomic_write_no_partial(data_dir, monkeypatch):
    store.update_session('s1', {'a': 1})
    def fail(*args):
        raise OSError('disk failure')
    monkeypatch.setattr(store.os, 'replace', fail)
    with pytest.raises(OSError):
        store.update_session('s1', {'a': 2})
    assert store.load_session('s1') == {'a': 1}
