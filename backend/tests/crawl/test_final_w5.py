from contextlib import closing
import sqlite3
import pytest
from app.context import store, versions
from app.crawl import control, report
from app.crawl.queue import CrawlQueue, DDL
from app.crawl.writer import DocWriter
from app.services import preprocessing
from tests.crawl.test_crawl_api import env, prepared


def test_gate_fork_does_not_inherit(env):
    root, _ = prepared(env)
    before = store.read_json(versions.version_dir('S', 'v1') / 'session.json')
    assert control.phase_state('S') == 'gate'
    assert versions.create_version('S', 'v1', 'stage2', '') == 'v2'
    assert store.load_session('S')['collectionId'] is None
    assert store.read_json(versions.version_dir('S', 'v1') / 'session.json') == before
    assert root.exists()


def paused_detail(env, reason='blocked'):
    root, snap = prepared(env)
    control.start_detail('S', snap)
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        q.connection.execute("UPDATE runs SET status='paused' WHERE kind='detail'")
        q.connection.execute("UPDATE urls SET status='leased' WHERE kw='beta'")
    store.write_json(root / 'worker_state.json', {'snapshot_id': snap, 'channels': {'fixture': {'status': 'paused_' + reason}}, 'paused_channels': ['fixture']})
    return root


@pytest.mark.parametrize('reason', ['blocked', 'parse_error'])
def test_finish_partial(env, reason, monkeypatch):
    root = paused_detail(env, reason)
    with closing(DocWriter(root / 'docs')) as writer:
        writer.write({'doc_id': 'collected', 'source': 'fixture', 'body': 'already collected full document', 'fetch_level': 'full'})
    assert control.status('S')['remaining_by_channel'] == {'fixture': 2}
    response = env.client.post('/crawl/S/finish-partial?version=v1')
    assert response.status_code == 200, response.text
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        assert q.counts()['skipped'] == 2
        assert report.can_finalize(q, control.latest_run(q))
    result = control.status('S')
    assert result['report']['channels']['fixture']['skipped'] == 2
    assert result['report']['channels']['fixture']['skip_reason'] == reason
    assert result['resumable'] is False
    assert result['progress']['target'] == result['progress']['done']
    assert control.phase_state('S') == 'done'
    saved = []
    monkeypatch.setattr(preprocessing, 'save_jsonl', lambda path, docs: saved.extend(docs))
    preprocessing.preprocess_data({'sid': 'S'})
    assert [doc['doc_id'] for doc in saved] == ['collected']
    assert versions.create_version('S', 'v1', 'stage3', '') == 'v2'
    assert store.load_session('S')['collectionId'] == 'c1'


@pytest.mark.parametrize('case', ['live', 'no_pause', 'list', 'version'])
def test_finish_refuses(env, case):
    root = paused_detail(env)
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        if case == 'live':
            q.connection.execute("UPDATE runs SET status='running' WHERE kind='detail'")
        if case == 'list':
            q.connection.execute("DELETE FROM runs WHERE kind='detail'")
    if case == 'no_pause':
        store.write_json(root / 'worker_state.json', {'channels': {}})
    response = env.client.post('/crawl/S/finish-partial?version=' + ('v2' if case == 'version' else 'v1'))
    assert response.status_code == 409
    assert not (root / 'report.json').exists()
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        assert q.counts().get('skipped', 0) == 0


def test_old_queue_migrates(tmp_path):
    path = tmp_path / 'queue.sqlite'
    with sqlite3.connect(path) as db:
        db.executescript(DDL.replace(",'skipped'", ''))
    with closing(CrawlQueue(path)) as q:
        sql = q.connection.execute("SELECT sql FROM sqlite_master WHERE name='urls'").fetchone()[0]
        assert "'skipped'" in sql


def test_migration_preserves_rows_and_snapshot(env):
    root, snap = prepared(env)
    path = root / 'queue.sqlite'
    with sqlite3.connect(path) as db:
        before = db.execute('SELECT * FROM urls ORDER BY url_norm').fetchall()
        db.execute('ALTER TABLE urls RENAME TO old_urls')
        ddl = DDL.split('CREATE TABLE IF NOT EXISTS urls (', 1)[1].split(';', 1)[0]
        db.execute('CREATE TABLE urls (' + ddl.replace(",'skipped'", ''))
        db.execute('INSERT INTO urls SELECT * FROM old_urls')
        db.execute('DROP TABLE old_urls')
    for _ in range(2):
        with closing(CrawlQueue(path)) as q:
            assert [tuple(r) for r in q.connection.execute('SELECT * FROM urls ORDER BY url_norm')] == before
            assert q.connection.execute('SELECT count(*) FROM snapshot_urls WHERE snapshot_id=?', (snap,)).fetchone()[0] == 2


def test_other_pending_channel_refuses_without_skipping(env):
    root = paused_detail(env)
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        q.connection.execute("UPDATE urls SET source='other' WHERE kw='beta'")
        q.connection.execute("UPDATE snapshot_urls SET source='other' WHERE url_norm LIKE '%/1'")
    assert env.client.post('/crawl/S/finish-partial').status_code == 409
    with closing(CrawlQueue(root / 'queue.sqlite')) as q:
        assert q.counts().get('skipped', 0) == 0
