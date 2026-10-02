from copy import deepcopy
from pathlib import Path
import shutil
import subprocess
from types import ModuleType

import os
import sqlite3
import time

import pytest

from app.config import settings
from app.context import store, versions
from app.model.infer import prepared_root
from app.segment.store import SegmentStore
from app.work.status import transaction


@pytest.fixture
def completed(data_dir):
    sid = 'completed-segment'
    store.update_session(sid, {'schemaVersion': 2, 'prep': {'status': 'done', 'derivedRef': {'collectionId': 'c1', 'prepKey': 'p_aaaaaaaaaaaa'}},
        'labeling': {'status': 'done', 'started': True, 'mode': 'llm', 'modelId': 'm', 'judgeRefs': ['j']},
        'training': {'status': 'done', 'exportRef': 'old'},
        'segment': {'status': 'done', 'run': 'old'}, 'completion': {'segmentDone': True, 'other': True},
        'drafts': {'segment': {'run': 'old'}, 'other': {'keep': [1, 2]}},
        'stageResults': {'stage3': {'keep': True}, 'stage5': {'keep': True}}})
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
    for path in (data_dir / 'llmcache' / sid / 'p_aaaaaaaaaaaa' / 'cache.json',
                 prepared_root(sid, store.read_json(root / 'session.json')) / 'nouns' / 'cache.json'):
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
    assert set(data['stale']) == {f'stage{s}' for s in range(stage, 9)}
    assert not (root / 'evidence').exists() and not (root / 'persona').exists()
    assert store.read_json(versions.version_dir(sid, 'v1') / 'session.json') == before
    assert SegmentStore.open(sid, 'v1').contexts()[0]['confirmed_at'] == 'yes'
    assert (data_dir / 'llmcache' / sid / 'p_aaaaaaaaaaaa' / 'cache.json').read_text() == 'keep'
    assert (prepared_root(sid, before) / 'nouns' / 'cache.json').read_text() == 'keep'


@pytest.mark.parametrize('stage', [3, 4, 5])
def test_restart_stage3_4_5_unchanged(completed, stage, data_dir, tmp_path_factory, monkeypatch):
    sid = completed
    parent = store.read_json(versions.version_dir(sid, 'v1') / 'session.json')
    # Execute the pre-T9 implementation against an identical isolated tree.
    legacy = ModuleType('versions_before_T9')
    # Frozen copy of versions.py at e0d124f, so a shallow CI checkout works.
    source = (Path(__file__).resolve().parents[1] / 'fixtures/legacy/versions_pre_t9.py').read_text(encoding='utf-8')
    exec(compile(source, 'e0d124f/versions.py', 'exec'), legacy.__dict__)
    baseline_dir = tmp_path_factory.mktemp('legacy') / 'data'
    shutil.copytree(data_dir, baseline_dir, symlinks=True)
    with monkeypatch.context() as patch:
        patch.setattr(settings, 'local_data_dir', str(baseline_dir))
        legacy.create_version(sid, 'v1', f'stage{stage}', '')
        old = store.read_json(legacy.version_dir(sid, 'v2') / 'session.json')
    versions.create_version(sid, 'v1', f'stage{stage}', '')
    root = versions.version_dir(sid, 'v2')
    data = store.read_json(root / 'session.json')
    assert set(data['stale']) == {f'stage{s}' for s in range(stage, 9)}
    def normalized(value, keys):
        value = deepcopy(value)
        for key in keys:
            value.pop(key, None)
        value.get('completion', {}).pop('segmentDone', None)
        value.get('drafts', {}).pop('segment', None)
        return value
    # Only D-237 changes and the timestamp may differ from the historical output.
    current = normalized(data, ('updatedAt', 'segment'))
    previous = normalized(old, ('updatedAt', 'segment'))
    for key in ('stage7', 'stage8'):
        current['stale'].pop(key)
    assert current == previous
    intended = ('version', 'parentVersion', 'restartFrom', 'updatedAt', 'stale',
                'prep', 'labeling', 'training', 'segment')
    assert normalized(data, intended) == normalized(parent, intended)
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


def test_compare_stage6_reports_confirmations_and_reset(completed):
    sid = completed
    root = versions.version_dir(sid, 'v1')
    store.write_json(root / 'segment/stage_6.json', {'dims': {'act_unknown': 2}})
    versions.create_version(sid, 'v1', 'stage7', '')
    assert versions.compare(sid, 'v1', 'v2', 'stage6')['same']
    # Report-only changes must be detected even outside the displayed summary.
    report_path = versions.version_dir(sid, 'v2') / 'segment/stage_6.json'
    store.write_json(report_path, {'dims': {'act_unknown': 2, 'coverage': {'doc': {'filled': 3}}}})
    report_diff = versions.compare(sid, 'v1', 'v2', 'stage6')
    assert not report_diff['same']
    assert report_diff['before']['report'] == report_diff['after']['report']
    store.write_json(report_path, {'dims': {'act_unknown': 2}})
    segment = SegmentStore.open(sid, 'v2')
    segment.confirm('personas', 'CL0-P0', {'name': 'new', 'desire': 'rest', 'goals': ['sleep']})
    segment.confirm('contexts', 'CL0-P0-C1', {'name': 'night', 'action': 'reserve'})
    diff = versions.compare(sid, 'v1', 'v2', 'stage6')
    assert not diff['same']
    assert diff['after']['personas']['items'][0]['name'] == 'new'
    assert diff['after']['personas']['items'][0]['desire'] == 'rest'
    assert diff['after']['personas']['items'][0]['goals'] == ['sleep']
    assert diff['after']['contexts']['items'][0]['action'] == 'reserve'
    assert diff['after']['clusters']['confirmed'] == 1
    store.write_json(versions.version_dir(sid, 'v2') / 'segment/stage_6.json', {'dims': {'act_unknown': 3}})
    assert versions.compare(sid, 'v1', 'v2', 'stage6')['after']['report']['dims']['act_unknown'] == 3
    versions.create_version(sid, 'v2', 'stage6', '')
    reset = versions.compare(sid, 'v2', 'v3', 'stage6')
    assert not reset['same'] and reset['after']['report'] is None
    assert reset['after']['personas'] == {'confirmed': 0, 'total': 0, 'items': []}
    assert not (versions.version_dir(sid, 'v3') / 'segment').exists()
