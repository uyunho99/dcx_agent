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


def test_manual_rollback_recovers_after_kill(macmini):
    m = macmini
    assert m.run_deploy()[0] == 0
    (m.root/'shared/data/sessions/value').write_text('after')
    history = (m.root/'shared/deploy-history').read_text()
    # switch_to runs after restoration and before history finalization.
    (m.bin/'mv').unlink()
    m.command('mv', '''import os,signal,sys
if sys.argv[-2].endswith('/current.tmp'):
    os.kill(os.getppid(), signal.SIGKILL)
    sys.exit(0)
os.execv('/bin/mv', ['/bin/mv']+sys.argv[1:])
''')
    r = ctl(m, 'rollback')
    assert r.returncode == -9
    assert (m.root/'shared/data/sessions/value').read_text() == 'original'
    assert (m.root/'shared/deploy-history').read_text() == history
    state = m.root/'shared/deploy-state'
    saved = state.read_text()
    assert saved.startswith(f'rolling-back {m.b} {m.a} ')
    (m.bin/'mv').unlink(); (m.bin/'mv').symlink_to('/bin/mv')
    assert m.run_deploy()[0] == 0, m.output
    assert m.current == m.a
    assert (m.root/'shared/last-failed-sha').read_text().strip() == m.b
    assert (m.root/'shared/deploy-history').read_text() == f'{m.a} -\n'
    assert m.logs[-1]['decision'] == 'rolled-back'
    assert not state.exists()
    assert not (m.root/'shared/maintenance').exists()
    backups = list((m.root/'shared/snapshots').glob('*-failed/sessions/value'))
    assert len(backups) == 1 and backups[0].read_text() == 'after'
    # Replay a crash after history rename: never remove another history row.
    state.write_text(saved)
    assert m.run_deploy()[0] == 0, m.output
    assert (m.root/'shared/deploy-history').read_text() == f'{m.a} -\n'
    assert not state.exists()
