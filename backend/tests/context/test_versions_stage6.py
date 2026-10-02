import os
import sqlite3
import time

import pytest

from app.context import store, versions
from app.segment.store import SegmentStore
from app.work.status import transaction


@pytest.fixture
def completed(data_dir):
    sid = 'completed-segment'
    store.update_session(sid, {'schemaVersion': 2, 'prep': {'status': 'done'},
        'labeling': {'status': 'done', 'started': True, 'mode': 'llm', 'modelId': 'm', 'judgeRefs': ['j']},
        'training': {'status': 'done', 'exportRef': 'old'},
        'segment': {'status': 'done', 'run': 'old'}, 'completion': {'segmentDone': True, 'other': True},
        'drafts': {'segment': {'run': 'old'}, 'other': {} }})
    root = versions.version_dir(sid, 'v1')
    store.write_json(root / 'stage_3.json', {'old': 3})
    store.write_json(root / 'stage_5.json', {'old': 5})
    with sqlite3.connect(root / 'labels.sqlite') as db:
        for table in ('final', 'queue', 'review_done', 'route_sync'):
            db.execute(f'CREATE TABLE {table} (doc_id TEXT)')
            db.execute(f"INSERT INTO {table} VALUES ('confirmed-doc')")
    segment = SegmentStore.open(sid, 'v1')
    segment.write_layers(clusters=[{'cluster_id': 'CL0', 'confirmed_at': 'yes'}],
        personas=[{'persona_id': 'CL0-P0', 'cluster_id': 'CL0', 'confirmed_at': 'yes'}],
        contexts=[{'context_id': 'CL0-P0-C1', 'persona_id': 'CL0-P0', 'confirmed_at': 'yes'}])
    segment.set_run('old')
    for name in ('evidence', 'persona'):
        store.write_json(root / name / 'result.json', {'old': True})
    for name in ('llmcache/cache', 'derived/nouns/cache'):
        path = data_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('keep')
    return sid


@pytest.mark.parametrize('stage', [3, 4, 5, 6])
def test_restart_from_3_4_5_6_invalidates_segment(completed, data_dir, stage):
    sid = completed
    before = store.read_json(versions.version_dir(sid, 'v1') / 'session.json')
    versions.create_version(sid, 'v1', f'stage{stage}', '')
    root = versions.version_dir(sid, 'v2')
    data = store.read_json(root / 'session.json')
    assert not (root / 'segment').exists()
    assert data['segment'] == {'status': 'stale'}
    assert 'segmentDone' not in data['completion'] and 'segment' not in data['drafts']
    assert {'stage6', 'stage7', 'stage8'} <= data['stale'].keys()
    assert not (root / 'evidence').exists() and not (root / 'persona').exists()
    assert store.read_json(versions.version_dir(sid, 'v1') / 'session.json') == before
    assert SegmentStore.open(sid, 'v1').contexts()[0]['confirmed_at'] == 'yes'
    assert (data_dir / 'llmcache/cache').read_text() == 'keep'
    assert (data_dir / 'derived/nouns/cache').read_text() == 'keep'


@pytest.mark.parametrize('stage', [3, 4, 5])
def test_restart_stage3_4_5_unchanged(completed, stage):
    sid = completed
    versions.create_version(sid, 'v1', f'stage{stage}', '')
    root = versions.version_dir(sid, 'v2')
    data = store.read_json(root / 'session.json')
    assert (root / 'stage_3.json').exists() == (stage > 3)
    assert not (root / 'stage_5.json').exists()
    assert data['prep']['status'] == ('stale' if stage == 3 else 'done')
    assert data['training'] == {'status': 'stale'}
    with sqlite3.connect(root / 'labels.sqlite') as db:
        for table in ('final', 'queue', 'review_done', 'route_sync'):
            assert db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == (1 if stage == 5 else 0)
        if stage <= 4:
            for table in ('stale_final', 'stale_queue'):
                assert db.execute(f'SELECT doc_id FROM {table}').fetchall() == [('confirmed-doc',)]
    with sqlite3.connect(versions.version_dir(sid, 'v1') / 'labels.sqlite') as db:
        assert db.execute('SELECT doc_id FROM final').fetchall() == [('confirmed-doc',)]
    if stage <= 4:
        assert data['labeling'] == {'mode': 'llm', 'modelId': 'm', 'judgeRefs': ['j'],
            'started': False, 'status': 'stale',
            'restartMessage': '이 라벨은 v1 기준입니다. LLM 판정은 재사용하고 사람 검수만 다시 합니다.'}
    else:
        assert data['labeling']['status'] == 'done'


@pytest.mark.parametrize('stage', [7, 8], ids=['stage7_keeps_segment', 'stage8_keeps_segment'])
def test_restart_keeps_segment(completed, stage):
    versions.create_version(completed, 'v1', f'stage{stage}', '')
    root = versions.version_dir(completed, 'v2')
    assert SegmentStore.open(completed, 'v2').contexts()[0]['confirmed_at'] == 'yes'
    data = store.read_json(root / 'session.json')
    assert data['segment']['status'] == 'done' and data['completion']['segmentDone']
    assert (root / 'evidence').exists() == (stage == 8)
    assert not (root / 'persona').exists()
    assert set(data['stale']) == {f'stage{s}' for s in range(stage, 9)}


def test_segment_worker_blocks_new_version(completed):
    with transaction(completed) as db:
        db.execute('INSERT INTO runs(run_id,version,kind,args_json,pid,state,heartbeat_at,started_at) VALUES (?,?,?,?,?,?,?,?)',
            ('running', 'v1', 'segment', '{}', os.getpid(), 'running', time.time(), time.time()))
    with pytest.raises(store.StoreError) as error:
        versions.create_version(completed, 'v1', 'stage6', '')
    assert error.value.status == 409
