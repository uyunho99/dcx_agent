from concurrent.futures import ThreadPoolExecutor
import os
import signal
import subprocess
import time

import pytest

from app.config import Settings
from app.work import runner


@pytest.fixture
def workers(data_dir, monkeypatch):
    children = []
    popen = subprocess.Popen

    def launch(command, **kwargs):
        assert command[1:3] == ['-m', 'app.work.worker']
        assert kwargs['start_new_session'] is True
        code = ('from app.work.worker import KINDS, main; '
                'from tests.fakes.fake_worker import run; '
                'KINDS.update(fake=run, judge=run); main()')
        child = popen([command[0], '-c', code, *command[3:]], **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(runner.subprocess, 'Popen', launch)
    yield children
    for child in children:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)


def wait_state(run_id, state):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        row = next(r for r in runner.status('s1') if r['runId'] == run_id)
        if row['state'] == state:
            return row
        time.sleep(.03)
    pytest.fail(f'Expected {state}, got {row}')


def test_double_start_spawns_one(workers):
    with ThreadPoolExecutor(max_workers=2) as pool:
        runs = list(pool.map(lambda _: runner.start('s1', 'v1', 'fake', {}), range(2)))
    assert runs[0]['runId'] == runs[1]['runId']
    assert len(workers) == 1
    wait_state(runs[0]['runId'], 'done')


def test_killed_worker_is_interrupted(workers):
    run = runner.start('s1', 'v1', 'fake', {})
    os.kill(workers[0].pid, signal.SIGKILL)
    workers[0].wait(timeout=5)
    wait_state(run['runId'], 'interrupted')


def test_two_labelers_run_independently(workers):
    jev = runner.start('s1', 'v1', 'judge', {'labeler': 'jev'})
    gpt = runner.start('s1', 'v1', 'judge', {'labeler': 'gpt'})
    assert jev['runId'] != gpt['runId']
    assert len(workers) == 2
    runner.request('s1', jev['runId'], 'pause')
    wait_state(jev['runId'], 'paused')
    wait_state(gpt['runId'], 'running')
    runner.request('s1', gpt['runId'], 'pause')
    wait_state(gpt['runId'], 'paused')
    runner.request('s1', jev['runId'], 'resume')
    wait_state(jev['runId'], 'running')
    wait_state(gpt['runId'], 'paused')


def test_pause_resume(workers):
    run = runner.start('s1', 'v1', 'fake', {})
    runner.request('s1', run['runId'], 'pause')
    wait_state(run['runId'], 'paused')
    assert runner.start('s1', 'v1', 'fake', {})['runId'] == run['runId']
    runner.request('s1', run['runId'], 'resume')
    wait_state(run['runId'], 'running')
    wait_state(run['runId'], 'done')


def test_settings_defaults(monkeypatch):
    monkeypatch.delenv('JEVMODEL_API_KEY', raising=False)
    settings = Settings(_env_file=None)
    assert settings.embed_model == 'voyage-4'
    assert settings.jev_rate_per_min == 120
    assert settings.jev_api_keys == []
    monkeypatch.setenv('JEVMODEL_API_KEY', ' first, second ,, ')
    assert Settings(_env_file=None).jev_api_keys == ['first', 'second']


def test_stop_paused_worker_and_restart(workers):
    run = runner.start('s1', 'v1', 'fake', {})
    runner.request('s1', run['runId'], 'pause')
    wait_state(run['runId'], 'paused')
    runner.request('s1', run['runId'], 'stop')
    wait_state(run['runId'], 'interrupted')
    assert runner.start('s1', 'v1', 'fake', {})['runId'] != run['runId']


def test_failed_worker(workers):
    run = runner.start('s1', 'v1', 'fake', {'duration': .05, 'fail': True})
    assert wait_state(run['runId'], 'failed')['error'] == 'RuntimeError'


def test_versions_are_independent(workers):
    first = runner.start('s1', 'v1', 'fake', {})
    second = runner.start('s1', 'v2', 'fake', {})
    assert first['runId'] != second['runId']
    assert len(workers) == 2


def test_stale_heartbeat_fences_live_worker(workers):
    from app.work.status import transaction
    run = runner.start('s1', 'v1', 'fake', {})
    runner.request('s1', run['runId'], 'pause')
    wait_state(run['runId'], 'paused')
    with transaction('s1') as db:
        db.execute('UPDATE runs SET heartbeat_at=?', (time.time() - 61,))
    wait_state(run['runId'], 'interrupted')
    workers[0].wait(timeout=5)
    wait_state(run['runId'], 'interrupted')


def test_spawn_failure_rolls_back(data_dir, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError('spawn failed')
    monkeypatch.setattr(runner.subprocess, 'Popen', fail)
    with pytest.raises(OSError):
        runner.start('s1', 'v1', 'fake', {})
    assert runner.status('s1') == []


def test_unknown_kind_fails_durably(data_dir):
    run = runner.start('s1', 'v1', 'unregistered', {})
    assert wait_state(run['runId'], 'failed')['error'] == 'KeyError'


def test_background_heartbeat(workers):
    run = runner.start('s1', 'v1', 'fake', {'sleep': 11})
    time.sleep(.3)
    initial = runner.status('s1')[0]['heartbeatAt']
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        row = runner.status('s1')[0]
        if row['heartbeatAt'] > initial:
            assert row['state'] == 'running'
            break
        time.sleep(.1)
    else:
        pytest.fail('No periodic heartbeat during blocked work')
    wait_state(run['runId'], 'done')


def test_empty_example_settings_use_defaults(monkeypatch):
    monkeypatch.setenv('EMBED_DIM', '')
    monkeypatch.setenv('JEV_BACKEND', '')
    assert Settings(_env_file=None).embed_dim == 1024


@pytest.mark.parametrize('kinds', [('evidence', 'persona'), ('persona', 'evidence'), ('segment', 'insight'), ('insight', 'evidence')])
def test_shared_launch_guard(data_dir, monkeypatch, kinds):
    from threading import Barrier
    from types import SimpleNamespace
    from app.context.store import StoreError
    barrier = Barrier(2)
    launches = []
    def launch(*args, **kwargs):
        launches.append(args)
        return SimpleNamespace(pid=os.getpid(), wait=lambda: 0, kill=lambda: None)
    monkeypatch.setattr(runner.subprocess, 'Popen', launch)
    def start(kind):
        barrier.wait()
        try:
            return runner.start('s1', 'v1', kind, {})
        except StoreError as exc:
            return exc
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(start, kinds))
    assert len(launches) == 1
    assert sum(isinstance(r, StoreError) for r in results) == 1
