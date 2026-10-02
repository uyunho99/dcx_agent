"""Manual commands reuse the isolated T2 harness."""
import subprocess
import pytest
from .conftest import SCRIPTS


def ctl(m, *args, **env):
    return subprocess.run([m.env['DCX_BASH'], str(SCRIPTS/'dcxctl'), *args],
                          env=dict(m.env, **env), text=True, capture_output=True, timeout=45)


def test_status_prints(macmini):
    m = macmini
    (m.root/'shared/last-failed-sha').write_text(m.b)
    m.lib('sha=test; log error')
    r = ctl(m, 'status')
    assert r.returncode == 0, r.stderr
    for text in ('current', m.a, 'release', 'last-failed-sha', m.b, 'deploy-history', 'deploy.log', 'error'):
        assert text in r.stdout


@pytest.mark.parametrize('explicit', [True, False])
def test_deploy_explicit_sha_clears_failed(macmini, explicit):
    m = macmini
    (m.root/'shared/last-failed-sha').write_text(m.b)
    r = ctl(m, 'deploy', *([m.b[:12]] if explicit else []))
    assert r.returncode == 0, r.stderr
    assert m.current == m.b
    assert not (m.root/'shared/last-failed-sha').exists()


def test_rollback(macmini):
    m = macmini
    assert m.run_deploy()[0] == 0
    (m.root/'shared/data/sessions/value').write_text('after')
    (m.root/'shared/data/work/runs.sqlite').write_text('work-after')
    (m.root/'events').write_text('')
    r = ctl(m, 'rollback')
    assert r.returncode == 0, r.stderr
    assert m.current == m.a
    assert (m.root/'shared/data/sessions/value').read_text() == 'original'
    assert (m.root/'shared/data/work/runs.sqlite').read_text() == 'work-before'
    assert (m.root/'shared/last-failed-sha').read_text().strip() == m.b
    assert m.logs[-1]['decision'] == 'rolled-back'
    assert (m.root/'events').read_text().splitlines() == ['stop', 'start']
    assert (m.root/'shared/deploy-history').read_text().splitlines() == [f'{m.a} -']
    assert ctl(m, 'rollback').returncode != 0


@pytest.mark.parametrize('missing', ['history', 'release', 'snapshot'])
def test_rollback_without_previous(macmini, missing):
    m = macmini
    if missing != 'history':
        assert m.run_deploy()[0] == 0
        import shutil
        if missing == 'release':
            shutil.rmtree(m.root/'releases'/m.a)
        else:
            shutil.rmtree(m.root/'shared/snapshots')
    before = (m.current, (m.root/'shared/deploy-history').read_text(), len(m.logs))
    r = ctl(m, 'rollback')
    assert r.returncode != 0
    assert '되돌릴 버전이 없습니다' in r.stderr
    assert before == (m.current, (m.root/'shared/deploy-history').read_text(), len(m.logs))
    assert not (m.root/'shared/last-failed-sha').exists()


def test_busy_lock_does_not_clear_failed(macmini):
    m = macmini
    import os
    lock = m.root/'shared/deploy.lock'
    lock.mkdir()
    (lock/'pid').write_text(str(os.getpid()))
    (m.root/'shared/last-failed-sha').write_text(m.b)
    assert ctl(m, 'deploy', m.b).returncode != 0
    assert (m.root/'shared/last-failed-sha').read_text() == m.b


def test_rollback_unhealthy(macmini):
    m = macmini
    assert m.run_deploy()[0] == 0
    r = ctl(m, 'rollback', DCX_FORCE_UNHEALTHY_SHA=m.a)
    assert r.returncode != 0
    assert m.logs[-1]['decision'] == 'unhealthy-both'
    assert (m.root/'shared/last-failed-sha').read_text().strip() == m.b
