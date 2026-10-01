import signal
import subprocess
import sys
from pathlib import Path


def test_kill_restart_no_duplicate_calls(tmp_path):
    # Real SIGKILL after row 40 commits; a 50-row lease leaves ten abandoned rows.
    backend_dir = Path(__file__).resolve().parents[2]
    script = r'''
import os, signal, sys, json
import httpx
from pathlib import Path
from types import SimpleNamespace
from app.config import settings
from app.context import store, versions
from app.label import judge
from app.label.votes import VoteCache
from app.label.jev import JevClient
from app.crawl.ratelimit import ChannelLimiter
from tests.fakes.fake_jev import FakeJev
ChannelLimiter.wait_start = lambda self: None
root = Path(sys.argv[1])
settings.local_data_dir = str(root)
settings.jev_api_keys = ['offline']
session = dict(projectContext={'oneLiner': 'context'}, prep={'derivedRef': {'collectionId': 'c1', 'prepKey': 'p_123456789abc'}})
store.write_json(versions.version_dir('session', 'v1') / 'session.json', session)
docs_root = root / 'derived/session/c1/p_123456789abc/docs'
docs_root.mkdir(parents=True, exist_ok=True)
(docs_root / '000.jsonl').write_text(''.join(json.dumps(dict(doc_id=f'd{i:03}', body='text')) + '\n' for i in range(100)))
fake = FakeJev()
def handle(request):
    with (root / 'calls').open('a') as out:
        out.write(request.headers['Idempotency-Key'] + '\n')
    return fake(request)
judge.JevClient = lambda keys, model: JevClient(keys, model, transport=httpx.MockTransport(handle))
put = VoteCache.put
def kill_after_commit(self, doc_id, payload):
    put(self, doc_id, payload)
    if sys.argv[2] == 'first' and self.counts()['done'] == 40:
        os.kill(os.getpid(), signal.SIGKILL)
VoteCache.put = kill_after_commit
ctx = SimpleNamespace(sid='session', version='v1', args={'labeler': 'jev'}, run_id=sys.argv[2], heartbeat=lambda *a: None, should_stop=lambda: False)
judge.run_worker(ctx)
'''
    first = subprocess.run([sys.executable, '-c', script, str(tmp_path), 'first'], cwd=backend_dir, capture_output=True, timeout=20)
    assert first.returncode == -signal.SIGKILL, first.stderr.decode()
    second = subprocess.run([sys.executable, '-c', script, str(tmp_path), 'second'], cwd=backend_dir, capture_output=True, timeout=20)
    assert second.returncode == 0, second.stderr.decode()
    calls = (tmp_path / 'calls').read_text().splitlines()
    assert len(calls) == len(set(calls)) == 100
    from app.label.votes import VoteCache
    assert VoteCache(next(tmp_path.glob('judge/session/*/jev/*'))).counts() == dict(pending=0, done=100, bad=0)


def test_live_leases_are_not_stolen(tmp_path):
    from app.label.votes import VoteCache
    first, second = VoteCache(tmp_path), VoteCache(tmp_path)
    first.seed(['a', 'b'])
    assert first.lease(1, 'first') == ['a']
    assert second.lease(2, 'second') == ['b']
    first.put('a', {'ok': True})
    first.seed(['a'])
    assert first.counts() == dict(pending=1, done=1, bad=0)


def test_leases_prioritize_fewer_attempts(tmp_path):
    from app.label.votes import VoteCache
    cache = VoteCache(tmp_path)
    cache.seed(['a', 'b', 'c'])
    assert cache.lease(1, 'run') == ['a']
    cache.fail('a', 'invalid_answer')
    assert cache.lease(3, 'run') == ['b', 'c', 'a']
