import json
import time
from types import SimpleNamespace
from contextlib import closing

import pytest
from app.config import settings
from app.context import store
from app.crawl import control, worker, report, gate
from app.crawl.adapters import REGISTRY
from app.crawl.adapters.base import AdapterBlocked, ListItem, ListPage, FetchedDoc
from app.crawl.filters import FilterConfig
from app.crawl.queue import CrawlQueue, KwMeta, QueueListItem
from app.crawl.ratelimit import ChannelLimiter
from tests.crawl.test_crawl_api import env, prepared


def test_stale_alive_worker(env, monkeypatch):
    monkeypatch.setattr(control.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout='unrelated'))
    control.start_list('S')
    root = control.collection_dir('S')
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        q.connection.execute("UPDATE runs SET heartbeat_at=?,started_at=?", (time.time()-120, time.time()-120))
        assert control._live(q) is None
    assert control.phase_state('S') == 'unfinished'


@pytest.mark.parametrize('kind', ['list', 'detail'])
def test_pause_resume(env, monkeypatch, kind):
    root, snap = prepared(env)
    class Blocked:
        def fetch(self, item):
            raise AdapterBlocked('HTTP 403 key=SENTINEL /private/corpus.csv')
        def list_page(self, kw, cursor):
            raise AdapterBlocked('HTTP 403 key=SENTINEL /private/corpus.csv')
    monkeypatch.setitem(REGISTRY, 'fixture', Blocked)
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        if kind == 'list':
            q.add_list_tasks([KwMeta(str(i), '', '', i) for i in range(40)], ['fixture'])
        else:
            q.add_urls([QueueListItem(f'fixture://aircon/{i+10}', source='fixture', kw='alpha') for i in range(40)])
            snap = q.take_snapshot()
    manifest = store.read_json(root / 'manifest.json')
    store.write_json(root / 'manifest.json', dict(manifest, snapshotId=snap))
    def run():
        if kind == 'list':
            worker.run_list('S', collection=root, limiters={'fixture': ChannelLimiter(1, 0)})
        else:
            worker.run_detail('S', snap, collection=root, backoff_s=0, limiters={'fixture': ChannelLimiter(1, 0)})
    run()
    assert control.latest_run(control.ReadQueue(root / 'queue.sqlite'))['status'] == 'paused'
    assert control.status('S')['status'] == 'interrupted'
    assert not (root / 'report.json').exists()
    assert control.phase_state('S') == 'unfinished'
    response = env.client.post('/crawl/S/resume', json={'min_interval_s': {'fixture': .001}})
    assert response.status_code == 200, response.text
    assert store.read_json(root / 'manifest.json')['config']['perChannel']['fixture']['min_interval_s'] == .001
    assert store.read_json(root / 'worker_state.json')['channels']['fixture']['status'] == 'running'
    class Good:
        def fetch(self, item):
            return [FetchedDoc('', 'body', [], None, {}, 'public', None)]
        def list_page(self, kw, cursor):
            return ListPage([], None, 0)
    monkeypatch.setitem(REGISTRY, 'fixture', Good)
    run()
    assert control.latest_run(control.ReadQueue(root / 'queue.sqlite'))['status'] == 'done'
    if kind == 'detail':
        assert control.status('S')['report']
        assert control.phase_state('S') == 'done'


def test_filter_crash_before_commit(tmp_path, monkeypatch):
    class Adapter:
        def list_page(self, kw, cursor):
            return ListPage([ListItem('fixture://aircon/0', '', '광고', None, {})], None, 1)
    monkeypatch.setitem(REGISTRY, 'fixture', Adapter)
    original = worker.check_list
    def crash(*args):
        raise RuntimeError('crash')
    monkeypatch.setattr(worker, 'check_list', crash)
    with pytest.raises(RuntimeError):
        worker.run_list('S', collection=tmp_path, keywords=['k'], sources=['fixture'])
    with closing(CrawlQueue(tmp_path / 'queue.sqlite')) as q:
        assert q.counts()['total'] == 0
        assert not q.connection.execute("SELECT 1 FROM list_tasks WHERE status='done'").fetchone()
    monkeypatch.setattr(worker, 'check_list', original)
    worker.run_list('S', collection=tmp_path, keywords=['k'], sources=['fixture'])
    with closing(CrawlQueue(tmp_path / 'queue.sqlite')) as q:
        assert q.counts()['filtered'] == 1


def test_document_counts(env):
    root, snap = prepared(env)
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        q.register_run('detail')
        rows = q.lease_urls(snap, 10, 60)
        for row, count in zip(rows, [200, 0]):
            q.mark_done(row.url_norm, row.source, count, fetch_level='full', access='public')
        cells = report.build_report(q)['matrix']
        assert cells['alpha']['fixture']['full'] == 200
        assert cells['beta']['fixture']['full'] == 0
        assert cells['alpha']['fixture']['urls_done'] == 1
        assert cells['alpha']['fixture']['urls_listed'] == 1


def test_safe_errors(env, monkeypatch, capsys):
    root, snap = prepared(env)
    secret = 'SENTINEL_SECRET'
    monkeypatch.setattr(settings, 'openai_api_key', secret)
    class Broken:
        def fetch(self, item):
            raise FileNotFoundError(f'/private/corpus.csv https://example.test/?key={secret}')
    monkeypatch.setitem(REGISTRY, 'fixture', Broken)
    worker.run_detail('S', snap, collection=root, backoff_s=0)
    payload = json.dumps(control.status('S')) + (root / 'report.json').read_text()
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        payload += str([tuple(r) for r in q.connection.execute('SELECT last_error FROM urls')])
    monkeypatch.setattr(worker, 'run_list', lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError(f'/private/corpus.csv ?key={secret}')))
    assert worker.main(['list', '--sid', 'S']) == 1
    payload += capsys.readouterr().err
    for unsafe in ['/private/corpus.csv', '?key=', secret]:
        assert unsafe not in payload


def test_context_channels_norm_and_fresh_flags(env):
    store.update_session('S', {'projectContext': __import__('tests.test_integration_stage0_2', fromlist=['CTX']).CTX, 'crawlConfig': control._Replacement({}),
        'keywords': [{'kw': 'Alpha', 'status': 'approved', 'crawlExcluded': True},
                     {'kw': 'a l p h a', 'status': 'approved'}]})
    control.start_list('S')
    root = control.collection_dir('S')
    assert len(store.read_json(root / 'meta.json')['keywords']) == 1
    assert not any(k.get('crawlExcluded') for k in store.load_session('S')['keywords'])


def test_gate_settings(env, monkeypatch):
    root, _ = prepared(env)
    monkeypatch.setattr(settings, 'gate_low_count', 1)
    monkeypatch.setattr(settings, 'gate_low_unique', 0)
    assert all(not r.badges for r in gate.compute_gate(control.ReadQueue(root / 'queue.sqlite')))


@pytest.mark.parametrize('command,should_kill', [('python -m app.crawl.worker detail', True), ('other-process', False)])
def test_stale_pid_killed_only_if_worker(env, monkeypatch, command, should_kill):
    control.start_list('S')
    killed = []
    monkeypatch.setattr(control.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout=command))
    monkeypatch.setattr(control.os, 'kill', lambda pid, sig: killed.append((pid, sig)))
    with closing(CrawlQueue(control.collection_dir('S') / 'queue.sqlite')) as q:
        q.connection.execute("UPDATE runs SET status='running',heartbeat_at=?", (time.time()-120,))
        assert control._live(q) is None
    assert bool(killed) == should_kill
    control.resume('S')
    assert len(env.calls) == 2


def test_record_page_rolls_back_filter_with_page(tmp_path, monkeypatch):
    with closing(CrawlQueue(tmp_path / 'queue.sqlite')) as q:
        q.register_run('list')
        q.add_list_tasks([KwMeta('k', '', '', 0)], ['fixture'])
        task = q.next_list_task()
        original = q._insert_urls
        def crash(db, rows):
            original(db, rows)
            raise RuntimeError('crash after insertion')
        monkeypatch.setattr(q, '_insert_urls', crash)
        with pytest.raises(RuntimeError):
            q.record_list_page(task, [ListItem('fixture://aircon/1', '', '', None, {})], None, filter_rules=['2'])
        assert q.counts()['total'] == 0
        assert q.connection.execute("SELECT status FROM list_tasks").fetchone()[0] == 'running'


def test_fixture_dates_wrap_every_year(tmp_path):
    from datetime import date, timedelta
    from app.crawl.adapters.fixture import _row_date
    today = date(2030, 2, 3)
    for row in (0, 364, 365, 10000):
        assert _row_date(row, today) == (today - timedelta(days=364) + timedelta(days=row % 365)).isoformat()


def test_gate_normalized_exclusion(env):
    prepared(env)
    control.save_gate('S', [' A L P H A '])
    assert store.load_session('S')['crawlConfig']['gateExclusions'] == ['alpha']


def test_context_channel_intersection(env, monkeypatch):
    from tests.test_integration_stage0_2 import CTX
    monkeypatch.setattr(control, 'available_sources', lambda: ['fixture', 'youtube'])
    store.update_session('S', {'projectContext': CTX, 'crawlConfig': control._Replacement({})})
    control.start_list('S')
    assert store.read_json(control.collection_dir('S') / 'manifest.json')['channels'] == ['fixture']


def test_done_with_pending_does_not_freeze_report(env):
    root, snap = prepared(env)
    control.start_detail('S', snap)
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        q.connection.execute("UPDATE runs SET status='done'")
    assert control.status('S')['report'] is None
    assert not (root / 'report.json').exists()


def test_start_list_confirms_only_stage2(env):
    store.update_session('S', {'stale': {'stage1': 'keep', 'stage2': 'clear'}})
    control.start_list('S')
    assert store.load_session('S')['stale'] == {'stage1': 'keep'}


def test_shared_multidoc_count(env):
    root, snap = prepared(env)
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        q.add_urls([QueueListItem('fixture://aircon/0', source='fixture', kw='beta', kw_order=1)])
        q.register_run('detail')
        for row in q.lease_urls(snap, 10, 60):
            q.mark_done(row.url_norm, row.source, 200 if row.kw == 'alpha' else 0,
                        fetch_level='snippet', access='restricted')
        result = report.build_report(q)
        for kw in ('alpha', 'beta'):
            assert result['matrix'][kw]['fixture']['snippet'] == 200
            assert result['matrix'][kw]['fixture']['restricted'] == 200
            assert result['counts'][kw]['fixture'] == 200


@pytest.mark.parametrize('body', [{'min_interval_s': {'fixture': -1}}, {'min_interval_s': {'unknown': 1}}])
def test_resume_validates_intervals(env, body):
    root, snap = prepared(env)
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        q.connection.execute("UPDATE runs SET status='paused'")
    assert env.client.post('/crawl/S/resume', json=body).status_code == 422


def test_resume_without_body_clears_pause(env):
    root, _ = prepared(env)
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        q.connection.execute("UPDATE runs SET status='paused'")
    store.write_json(root / 'worker_state.json', {'kind': 'list', 'channels': {
        'fixture': {'status': 'paused_blocked', 'attempts': 20, 'blocked': 20, 'parse_errors': 0}}})
    assert env.client.post('/crawl/S/resume').status_code == 200
    assert store.read_json(root / 'worker_state.json')['channels']['fixture']['status'] == 'running'
