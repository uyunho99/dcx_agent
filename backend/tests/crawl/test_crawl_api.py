"""T14 contracts; all fixtures are local and subprocesses are injected."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import os
import shutil
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from app.config import settings
from app.context import store
from app.crawl import control, gate, report, worker
from app.crawl.adapters import REGISTRY
from app.crawl.adapters.base import ListPage
from app.crawl.queue import CrawlQueue, KwMeta, QueueListItem
from app.main import app


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'local_data_dir', str(tmp_path))
    monkeypatch.setattr(control, 'available_sources', lambda: ['fixture'])
    store.update_session('S', {'schemaVersion': 2, 'sid': 'S', 'keywords': [
        {'kw': 'alpha', 'axis': 'a', 'sub': 's', 'status': 'approved'},
        {'kw': 'beta', 'axis': 'b', 'sub': 't', 'status': 'approved'}],
        'crawlConfig': {'channels': ['fixture']}})
    calls = []
    def spawn(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(pid=987654321)
    monkeypatch.setattr(control.subprocess, 'Popen', spawn)
    monkeypatch.setattr(control, 'pid_alive', lambda pid: pid == 987654321)
    return SimpleNamespace(root=tmp_path, calls=calls, client=TestClient(app))


def prepared(env):
    control.start_list('S')
    root = control.collection_dir('S')
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        q.connection.execute("UPDATE runs SET status='done'")
        q.connection.execute("UPDATE list_tasks SET status='done'")
        for i, kw in enumerate(['alpha', 'beta']):
            q.add_urls([QueueListItem(f'fixture://aircon/{i}', source='fixture', kw=kw, kw_order=i)])
        snap = q.take_snapshot()
    env.calls.clear()
    return root, snap


def test_gate_badges(tmp_path):
    with closing(CrawlQueue(tmp_path / 'queue.sqlite')) as q:
        q.add_list_tasks([KwMeta(k, 'a', 's', i) for i, k in enumerate(['zero', 'low', 'shared'])], ['fixture'])
        q.add_urls([QueueListItem('fixture://aircon/1', source='fixture', kw=k, kw_order=i) for i, k in enumerate(['low', 'shared'])])
        rows = {r.kw: r for r in gate.compute_gate(q)}
        assert 'zero' in rows['zero'].badges
        assert 'low' in rows['low'].badges
        assert 'low_unique' in rows['shared'].badges
        assert rows['low'].axis == 'a'


def test_gate_excludes_then_detail_skips(env):
    root, snap = prepared(env)
    assert env.client.put('/crawl/S/gate', json={'exclusions': ['alpha']}).status_code == 200
    control.start_detail('S', snap)
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        assert q.counts()['excluded'] == 1
        q.connection.execute("UPDATE runs SET status='done'")
        q.register_run('detail')
        assert [r.kw for r in q.lease_urls(snap, 10, 60)] == ['beta']


def test_gate_exclusions_survive_config_save_then_detail(env):
    root, snap = prepared(env)
    assert env.client.put('/crawl/S/gate', json={'exclusions': ['alpha']}).status_code == 200
    assert env.client.put('/crawl/S/config', json={
        'channels': ['fixture'], 'perChannel': {'fixture': {}}
    }).status_code == 200
    assert env.client.post('/crawl/S/detail', json={'snapshot_id': snap}).status_code == 200
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        assert q.counts()['excluded'] == 1
        q.connection.execute("UPDATE runs SET status='done'")
        q.register_run('detail')
        assert [r.kw for r in q.lease_urls(snap, 10, 60)] == ['beta']


def test_report_matrix_fields(env):
    root, _ = prepared(env)
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        assert set(report.build_report(q)['matrix']['alpha']['fixture']) == {'listed', 'filtered', 'excluded', 'full', 'snippet', 'restricted', 'unique', 'urls_listed', 'urls_done'}


def test_status_interrupted_when_pid_dead(env, monkeypatch):
    control.start_list('S')
    monkeypatch.setattr(control, 'pid_alive', lambda pid: False)
    assert control.status('S')['status'] == 'interrupted'
    assert control.activity('S')['kind'] == 'crawl_list'


def test_no_double_spawn(env):
    _, snap = prepared(env)
    control.start_detail('S', snap)
    control.start_detail('S', snap)
    assert len(env.calls) == 1
    args, opts = env.calls[0]
    assert opts['start_new_session'] is True
    assert args[0][1:4] == ['-m', 'app.crawl.worker', 'detail']


def test_query_never_contains_bk(env, monkeypatch):
    seen = []
    class Adapter:
        def list_page(self, kw, cursor):
            seen.append(kw)
            return ListPage([], None, 0)
    monkeypatch.setitem(REGISTRY, 'fixture', Adapter)
    store.update_session('S', {'bk': 'brand'})
    control.start_list('S')
    root = control.collection_dir('S')
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        q.connection.execute("UPDATE runs SET status='done'")
    worker.run_list('S', collection=root)
    assert seen == ['alpha', 'beta']
    assert all('bk' not in kw and 'brand' not in kw for kw in seen)


def test_old_crawl_endpoints_removed(env):
    assert env.client.post('/crawl', json={}).status_code == 404
    assert env.client.get('/status/S').status_code == 404


def test_report_built_on_phase_end_only(env):
    root, snap = prepared(env)
    control.start_detail('S', snap)
    control.status('S')
    assert not (root / 'report.json').exists()
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        q.connection.execute("UPDATE runs SET status='done'")
        q.connection.execute("UPDATE urls SET status='done'")
    control.status('S')
    before = (root / 'report.json').stat().st_mtime_ns
    control.status('S')
    assert (root / 'report.json').stat().st_mtime_ns == before


def test_gate_save_does_not_start_detail(env):
    _, snap = prepared(env)
    assert env.client.put('/crawl/S/gate', json={'exclusions': ['alpha']}).status_code == 200
    assert not env.calls
    assert env.client.post('/crawl/S/detail', json={'snapshot_id': snap}).status_code == 200
    assert len(env.calls) == 1


def test_per_keyword_counts_include_shared(env):
    root, _ = prepared(env)
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        q.connection.execute("DELETE FROM urls WHERE kw='beta'")
        q.connection.execute("DELETE FROM url_hits WHERE kw='beta'")
        q.add_urls([QueueListItem('fixture://aircon/0', source='fixture', kw='beta', kw_order=1)])
        rows = {r.kw: r for r in gate.compute_gate(q)}
        assert (rows['alpha'].listed, rows['beta'].listed) == (1, 1)
        result = report.build_report(q)
        assert result['matrix']['beta']['fixture']['listed'] == 1
        assert result['totals']['total'] == 1


def test_added_keywords_creates_child_collection(env):
    root, _ = prepared(env)
    before = (root / 'meta.json').read_bytes()
    old = store.load_session('S')['keywords']
    store.update_session('S', {'keywords': old + [{'kw': f'new{i}', 'status': 'approved'} for i in range(12)]})
    result = control.start_list('S', mode='added-keywords')
    child = control.collection_dir('S')
    assert result['collectionId'] == 'c2'
    assert store.read_json(child / 'meta.json')['parent'] == 'c1'
    with closing(CrawlQueue.open_readonly(child / 'queue.sqlite')) as db:
        assert {r[0] for r in db.execute('SELECT kw FROM list_tasks')} == {f'new{i}' for i in range(12)}
    assert (root / 'meta.json').read_bytes() == before


def test_new_list_creates_new_collection(env):
    root, _ = prepared(env)
    (root / 'docs').mkdir()
    (root / 'docs' / 'part.jsonl').write_text('preserve')
    assert control.start_list('S')['collectionId'] == 'c2'
    assert (root / 'docs' / 'part.jsonl').read_text() == 'preserve'


def test_concurrent_detail_start_single_worker(env):
    _, snap = prepared(env)
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda _: control.start_detail('S', snap), range(2)))
    assert len(env.calls) == 1


def test_report_from_queue_only(env):
    root, _ = prepared(env)
    (root / 'docs').mkdir()
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        expected = report.build_report(q)['matrix']
        shutil.rmtree(root / 'docs')
        assert report.build_report(q)['matrix'] == expected


def test_progress_counters_from_queue(env):
    root, snap = prepared(env)
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        run = q.register_run('detail')
        for row in q.lease_urls(snap, 10, 60):
            q.mark_done(row.url_norm, row.source, 1, fetch_level='snippet', access='restricted')
        q.finish_run(run, 'done')
        expected = q.counts()
    p = env.client.get('/crawl/S/status').json()['progress']
    assert (p['done'], p['snippet'], p['restricted']) == (expected['done'], expected['fetch_level']['snippet'], expected['access']['restricted'])


def test_config_validation_and_readonly(env):
    good = {'sources': ['fixture'], 'dateFrom': '2025-01-01', 'dateTo': '2026-01-01',
            'adWords': ['ad'], 'includeSources': [], 'excludeSources': []}
    response = env.client.put('/crawl/S/config', json=good)
    assert response.status_code == 200
    assert response.json()['crawlConfig']['product_name_filter'] is False
    for patch in ({'sources': ['missing']}, {'dateTo': '2024-01-01'}, {'product_name_filter': 'invalid'}):
        result = env.client.put('/crawl/S/config', json=dict(good, **patch))
        assert result.status_code == 422
        assert result.json()['error']['kind'] == 'validation'
    for path, body in [('config', good), ('gate', {'exclusions': []})]:
        assert env.client.put(f'/crawl/S/{path}?version=v99', json=body).status_code == 409
    assert env.client.post('/crawl/S/list?version=v99').status_code == 409
    assert not env.calls


def test_stop_resume_reclaims_and_preserves_snapshot(env, monkeypatch):
    root, snap = prepared(env)
    control.start_detail('S', snap)
    sent = []
    monkeypatch.setattr(control.os, 'kill', lambda pid, sig: sent.append((pid, sig)))
    assert control.stop('S')['status'] == 'stopping'
    import signal
    assert sent == [(987654321, signal.SIGTERM)]
    monkeypatch.setattr(control, 'pid_alive', lambda pid: False)
    assert control.resume('S')['kind'] == 'detail'
    assert env.calls[-1][0][0][-2:] == ['--snapshot', snap]


def test_partial_list_snapshot_cannot_start_detail(env):
    root, snap = prepared(env)
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        q.connection.execute("UPDATE runs SET status='stopped'")
    assert env.client.post('/crawl/S/detail', json={'snapshot_id': snap}).status_code == 409
    assert not env.calls


def test_finished_collection_rejects_mutation(env):
    root, snap = prepared(env)
    control.start_detail('S', snap)
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        q.connection.execute("UPDATE runs SET status='done'")
    control.status('S')
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    assert env.client.post('/crawl/S/detail', json={'snapshot_id': snap}).status_code == 409
    assert env.client.post('/crawl/S/resume').status_code == 409
    assert env.client.put('/crawl/S/gate', json={'exclusions': []}).status_code == 409
    assert {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()} == before


def test_end_to_end_fixture(env, monkeypatch):
    corpus = env.root / 'sample.csv'
    corpus.write_text('review\nalpha beta useful\nalpha practical\n')
    monkeypatch.setattr(settings, 'fixture_corpus_path', str(corpus))
    env.client.put('/crawl/S/config', json={'channels': ['fixture'], 'dateFrom': None, 'dateTo': None, 'adWords': [], 'excludeSources': []})
    control.start_list('S')
    root = control.collection_dir('S')
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        q.connection.execute("UPDATE runs SET status='done'")
    snap = worker.run_list('S', collection=root)
    assert control.status('S')['gate'][0]['listed'] >= 1
    control.save_gate('S', ['beta'])
    control.start_detail('S', snap)
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        q.connection.execute("UPDATE runs SET status='done'")
    worker.run_detail('S', snap, collection=root)
    result = control.status('S')
    assert result['status'] == 'done'
    assert result['report']['totals']['doc_count'] == 2
    assert result['report']['matrix']['beta']['fixture']['full'] == 1
    assert control.activity('S') is None


def test_real_subprocess_registration(env, monkeypatch):
    import subprocess
    import time
    # Restore only Popen/pid check; use the worker's existing offline hook.
    monkeypatch.undo()
    monkeypatch.setattr(settings, 'local_data_dir', str(env.root))
    monkeypatch.setattr(control, 'available_sources', lambda: ['fixture'])
    module = env.root / 't14_adapter.py'
    module.write_text('from app.crawl.adapters import REGISTRY\n'
                      'from app.crawl.adapters.base import ListPage\n'
                      'class Adapter:\n'
                      ' def list_page(self, kw, cursor): return ListPage([], None, 0)\n'
                      'REGISTRY["fixture"] = Adapter\n')
    monkeypatch.setenv('DCX_TEST_ADAPTER_MODULE', 't14_adapter')
    monkeypatch.setenv('PYTHONPATH', str(env.root) + os.pathsep + str(control.Path(__file__).resolve().parents[2]))
    original = subprocess.Popen
    children = []
    def spawn(*args, **kwargs):
        child = original(*args, **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(control.subprocess, 'Popen', spawn)
    try:
        result = control.start_list('S')
        assert result['collectionId'] == store.load_session('S')['collectionId']
        children[-1].wait(timeout=15)
        assert children[-1].returncode == 0
        state = control.status('S')
        assert state['status'] == 'done'
        assert state['snapshot_id']
        control.start_detail('S', state['snapshot_id'])
        children[-1].wait(timeout=15)
        assert children[-1].returncode == 0
        assert control.status('S')['report']['totals']['total'] == 0
        assert store.load_session('S')['step'] == 'crawl-done'
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=15)


def test_activity_without_queue_is_none(env):
    store.update_session('S', {'collectionId': 'c1'})
    assert control.activity('S') is None


def test_gate_thresholds_and_estimate(env):
    root, _ = prepared(env)
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        q.add_urls([QueueListItem(f'fixture://aircon/{i+10}', source='fixture', kw='alpha', kw_order=0) for i in range(9)])
        row = next(r for r in gate.compute_gate(q) if r.kw == 'alpha')
        assert row.after_filter == 10
        assert 'low' not in row.badges
        assert gate.estimate(q, {'gateExclusions': ['alpha']})['urls'] == 1


def test_collection_freezes_config_and_gate(env):
    env.client.put('/crawl/S/config', json={'channels': ['fixture'], 'product_name_filter': True,
                                          'adWords': ['ad'], 'perChannel': {'fixture': {'concurrency': 2}}})
    root, snap = prepared(env)
    manifest = store.read_json(root / 'manifest.json')
    assert manifest['config']['filters']['product_name_filter'] is True
    assert manifest['config']['filters']['ad_words'] == ['ad']
    assert manifest['config']['channel_limits']['fixture']['concurrency'] == 2
    before = control.status('S')['gate']
    control.start_detail('S', snap)
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        q.connection.execute("UPDATE urls SET status='filtered'")
    assert control.status('S')['gate'] == before


def test_status_after_crawl_leaves_session_unchanged(env):
    root, snap = prepared(env)
    control.start_detail('S', snap)
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        q.connection.execute("UPDATE runs SET status='done'")
    store.update_session('S', {'step': 'preprocess-setup'})
    path = store.session_dir('S') / 'session.json'
    before = path.read_bytes()
    updated = store.load_session('S')['updatedAt']
    for _ in range(5):
        assert env.client.get('/crawl/S/status').status_code == 200
    assert path.read_bytes() == before
    assert store.load_session('S')['updatedAt'] == updated


def test_empty_mutation_does_not_write(env, monkeypatch):
    def unexpected_write(*args):
        pytest.fail('empty patch wrote session')
    monkeypatch.setattr(store, 'write_json', unexpected_write)
    assert control._mutate('S', lambda session: ({}, {'status': 'idle'})) == {'status': 'idle'}


def test_stale_activity_does_not_block_version(env):
    from app.context import versions
    control.start_list('S')
    with closing(CrawlQueue(control.collection_dir('S') / 'queue.sqlite')) as q:
        q.connection.execute('UPDATE runs SET heartbeat_at=0')
    assert control.status('S')['status'] == 'interrupted'
    assert control.activity('S')['status'] == 'interrupted'
    assert versions.create_version('S', 'v1', 'stage2', '') == 'v2'


def test_corrupt_queue_only_marks_its_session_unreadable(env):
    control.start_list('S')
    (control.collection_dir('S') / 'queue.sqlite').write_bytes(b'corrupt database')
    store.update_session('healthy', {'schemaVersion': 2, 'sid': 'healthy'})
    result = env.client.get('/sessions').json()
    assert result['status'] == 'ok'
    rows = {row['sid']: row for row in result['sessions']}
    assert set(rows) == {'S', 'healthy'}
    assert rows['S']['activity']['status'] == 'unreadable'
    assert rows['healthy']['activity'] is None


@pytest.mark.parametrize('phase', ['list', 'detail'])
def test_done_crawl_has_no_activity_badge(env, phase):
    root, snap = prepared(env)
    if phase == 'detail':
        control.start_detail('S', snap)
        with closing(CrawlQueue(root / 'queue.sqlite')) as q:
            q.connection.execute("UPDATE runs SET status='done'")
    assert control.activity('S') is None
    assert env.client.get('/sessions').json()['sessions'][0]['activity'] is None


def test_estimate_cached_at_gate_and_never_computed_during_detail(env, monkeypatch):
    root, snap = prepared(env)
    original = gate.estimate
    calls = []
    def counted(*args):
        calls.append(True)
        return original(*args)
    monkeypatch.setattr(gate, 'estimate', counted)
    first = control.status('S')['estimate']
    assert first['urls'] == 2
    assert store.read_json(root / 'gate.json')['estimate'] == first
    assert control.status('S')['estimate'] == first
    assert len(calls) == 1
    control.save_gate('S', ['alpha'])
    assert control.status('S')['estimate']['urls'] == 1
    control.start_detail('S', snap)
    calls.clear()
    for _ in range(5):
        assert control.status('S')['progress']['target'] == 1
    assert not calls


@pytest.mark.parametrize('collected', [False, True])
def test_status_defaults_and_available_sources(env, collected):
    from app.crawl.filters import DEFAULT_AD_WORDS, DEFAULT_EXCLUDE_SOURCES
    if collected:
        prepared(env)
    response = env.client.get('/crawl/S/status')
    assert response.status_code == 200
    data = response.json()
    assert data['defaults'] == {'adWords': DEFAULT_AD_WORDS, 'excludeSources': DEFAULT_EXCLUDE_SOURCES}
    assert data['available_sources'] == ['fixture']
    if not collected:
        assert data['collection_keywords'] == []
        assert data['added_keywords_count'] == 0


def test_status_collection_settings_without_collection(env):
    response = env.client.get('/crawl/S/status')
    assert response.status_code == 200
    assert response.json()['collection_channels'] == []
    assert response.json()['min_interval_s'] == {}


@pytest.mark.parametrize('config, expected', [
    ({}, {'fixture': 0, 'youtube': 0, 'clien': 1, 'ppomppu': 1}),
    ({'channel_limits': {'clien': {'min_interval_s': 3}}},
     {'fixture': 0, 'youtube': 0, 'clien': 3, 'ppomppu': 1}),
    ({'channel_limits': {'clien': {'min_interval_s': 3}},
      'perChannel': {'clien': {'min_interval_s': 5}}},
     {'fixture': 0, 'youtube': 0, 'clien': 5, 'ppomppu': 1}),
])
def test_status_collection_settings_from_manifest(env, monkeypatch, config, expected):
    sources = ['fixture', 'youtube', 'clien', 'ppomppu']
    monkeypatch.setattr(control, 'available_sources', lambda: sources)
    store.update_session('S', {'crawlConfig': {'channels': sources}})
    control.start_list('S')
    root = control.collection_dir('S')
    manifest = store.read_json(root / 'manifest.json')
    store.write_json(root / 'manifest.json', dict(manifest, config=config))
    store.update_session('S', {'crawlConfig': {
        'channels': ['fixture'], 'perChannel': {'fixture': {'min_interval_s': 99}}}})
    response = env.client.get('/crawl/S/status')
    assert response.status_code == 200
    assert response.json()['collection_channels'] == sources
    assert response.json()['min_interval_s'] == expected


def test_status_collection_interval_after_resume(env, monkeypatch):
    control.start_list('S')
    monkeypatch.setattr(control, 'pid_alive', lambda pid: False)
    response = env.client.post('/crawl/S/resume', json={'min_interval_s': {'fixture': 2.5}})
    assert response.status_code == 200
    response = env.client.get('/crawl/S/status')
    assert response.status_code == 200
    assert response.json()['collection_channels'] == ['fixture']
    assert response.json()['min_interval_s'] == {'fixture': 2.5}


def test_save_config_replaces_removed_channel(env, monkeypatch):
    monkeypatch.setattr(control, 'available_sources', lambda: ['fixture', 'youtube'])
    first = {'channels': ['fixture', 'youtube'], 'perChannel': {'fixture': {}, 'youtube': {}}}
    assert env.client.put('/crawl/S/config', json=first).status_code == 200
    store.update_session('S', {'crawlConfig': {'gateExclusions': ['alpha']}})
    second = {'channels': ['fixture'], 'perChannel': {'fixture': {}}}
    response = env.client.put('/crawl/S/config', json=second)
    assert response.status_code == 200
    saved = store.load_session('S')['crawlConfig']
    assert 'youtube' not in saved['perChannel']
    assert saved['gateExclusions'] == ['alpha']
    assert saved == response.json()['crawlConfig']
    user_config = {key: value for key, value in saved.items() if key != 'gateExclusions'}
    assert env.client.put('/crawl/S/config', json=user_config).status_code == 200
    assert store.load_session('S')['crawlConfig'] == saved


def test_status_added_keywords_across_chain_normalized(env):
    prepared(env)
    old = store.load_session('S')['keywords']
    store.update_session('S', {'keywords': old + [{'kw': '가 나', 'status': 'approved'}]})
    control.start_list('S', mode='added-keywords')
    store.update_session('S', {'keywords': [
        {'kw': ' AL PHA ', 'status': 'approved'},
        {'kw': '가나', 'status': 'approved'},
        {'kw': 'new', 'status': 'approved'},
        {'kw': 'ignored', 'status': 'candidate'},
    ]})
    data = env.client.get('/crawl/S/status').json()
    assert set(data['collection_keywords']) == {'alpha', 'beta', '가 나'}
    assert data['added_keywords_count'] == 1
