"""Load with PYTEST_PLUGINS=tests.label.perf_stability for the perf suite.

Kept in the stability job's allowed test directory; the shared perf test is
unchanged. Adds component timings and a genuinely fresh-process measurement.
"""
from pathlib import Path
import subprocess
import sys
from time import perf_counter

import pytest


@pytest.fixture(autouse=True)
def stability_perf_timings(request, monkeypatch):
    if request.node.name != 'test_overview_310000_documents':
        yield
        return
    from app.config import settings
    from app.label import overview
    sid, _ = request.getfixturevalue('large_session')
    client = request.getfixturevalue('client')
    original_get = client.get
    index, estimate = overview.index_documents, overview._estimate
    times = {'index': 0., 'estimate': 0.}
    def timed(name, function):
        def call(*args, **kwargs):
            start = perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                times[name] += perf_counter() - start
        return call
    monkeypatch.setattr(overview, 'index_documents', timed('index', index))
    measured_estimate = timed('estimate', estimate)
    measured_estimate.cache_clear = estimate.cache_clear
    monkeypatch.setattr(overview, '_estimate', measured_estimate)
    calls = []
    def get(*args, **kwargs):
        times.update(index=0., estimate=0.)
        response = original_get(*args, **kwargs)
        name = 'cold' if not calls else 'warm'
        calls.append(name)
        print(f"overview {name} index={times['index']:.6f}s estimate={times['estimate']:.6f}s")
        return response
    monkeypatch.setattr(client, 'get', get)
    yield
    # New interpreter: persisted index, empty in-process estimate cache.
    script = r'''
import socket, sys
from time import perf_counter
from unittest.mock import patch

def offline(*args, **kwargs):
    raise AssertionError('Performance measurement must stay offline')
socket.socket.connect = offline
with patch('pydantic_settings.sources.DotEnvSettingsSource.__call__', return_value={}):
    from app.config import settings
settings.local_data_dir = sys.argv[1]
settings.storage = 'local'
from app.context import store
from app.label import overview
from app.routers.prep import _root  # Match app startup before endpoint timing.
sid = sys.argv[2]
data = store.load_session(sid)
labels = overview.labels_for(sid, data)
ref = data['prep']['derivedRef']
with labels._db() as db:
    for path in (_root(sid, ref['collectionId'], ref['prepKey']) / 'docs').glob('*.jsonl'):
        stat = path.stat()
        assert db.execute('SELECT stamp FROM document_files WHERE path=?',
                          (str(path),)).fetchone()[0] == f'{stat.st_mtime_ns}:{stat.st_size}'
assert overview._estimate.cache_info().currsize == 0
timings = {}
for name in ('index_documents', '_estimate'):
    original = getattr(overview, name)
    def timed(*args, _name=name, _original=original, **kwargs):
        start = perf_counter()
        try:
            return _original(*args, **kwargs)
        finally:
            timings[_name] = timings.get(_name, 0.) + perf_counter() - start
    setattr(overview, name, timed)
start = perf_counter()
result = overview.overview(sid)
elapsed = perf_counter() - start
assert result['total'] == 310000 and result['accepted'] == 279000
print(f"overview fresh-process indexed total={elapsed:.6f}s index={timings['index_documents']:.6f}s estimate={timings['_estimate']:.6f}s")
'''
    result = subprocess.run([sys.executable, '-c', script, settings.local_data_dir, sid],
                            cwd=Path(__file__).resolve().parents[2],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    print(result.stdout, end='')
