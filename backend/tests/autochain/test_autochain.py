from app import autochain


def test_disabled_session_does_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(autochain.store, 'load_session', lambda sid: {'autoChain': False})
    monkeypatch.setattr('app.routers.prep.run', lambda sid: calls.append('prep'))
    autochain.after_crawl('s')
    assert calls == []


def test_crawl_then_prep_then_labeling(monkeypatch):
    calls, notes = [], []
    monkeypatch.setattr(autochain.store, 'load_session', lambda sid: {'autoChain': True})
    monkeypatch.setattr(autochain.store, 'update_session', lambda sid, patch: notes.append(patch['autoChainStatus']))
    monkeypatch.setattr('app.routers.prep.run', lambda sid: calls.append('prep') or {'status': 'running'})
    monkeypatch.setattr('app.routers.labeling_v2.start', lambda sid, version=None: calls.append('label'))
    autochain.after_crawl('s')
    assert calls == ['prep'] and notes[-1]['stage'] == 'prep'
    autochain.after_prep('s', 'v1')
    assert calls == ['prep', 'label'] and notes[-1] == {**notes[-1], 'stage': 'labeling', 'state': 'running'}


def test_reused_preparation_starts_labeling_and_failures_are_recorded(monkeypatch):
    calls, notes = [], []
    monkeypatch.setattr(autochain.store, 'load_session', lambda sid: {'autoChain': True})
    monkeypatch.setattr(autochain.store, 'update_session', lambda sid, patch: notes.append(patch['autoChainStatus']))
    monkeypatch.setattr('app.routers.prep.run', lambda sid: {'status': 'done'})
    def fail(sid, version=None):
        raise RuntimeError('prep not ready')
    monkeypatch.setattr('app.routers.labeling_v2.start', fail)
    autochain.after_crawl('s')
    assert notes[-1]['stage'] == 'labeling' and notes[-1]['state'] == 'failed' and 'prep not ready' in notes[-1]['error']
