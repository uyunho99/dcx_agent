"""Persistence contracts for the stage-six foundation."""
import sqlite3

import numpy as np
import pytest

from app.context.store import StoreError
from app.context.versions import version_dir
from app.segment.store import SegmentStore


@pytest.fixture
def layers(data_dir):
    store = SegmentStore.open('segment', 'v1')
    store.write_layers(
        clusters=[dict(cluster_id=f'CL{i}', name_draft=f'draft {i}', keywords=['냉방'],
                       requests=[], quality={'cohesion': .8}) for i in (10, 2, 0)],
        personas=[dict(persona_id='CL0-P0', cluster_id='CL0', name_draft='persona',
                       desire_draft='desire draft', goals_draft=['goal draft']),
                  dict(persona_id='CL2-P0', cluster_id='CL2')],
        contexts=[dict(context_id=f'CL0-P0-C{i}', persona_id='CL0-P0',
                       name_draft='context', action_draft='action draft',
                       centroid=np.array([.6, .8], dtype=np.float32)) for i in (0, 1)] +
                 [dict(context_id='CL2-P0-C0', persona_id='CL2-P0')],
        docs=[dict(doc_id=f'd{i}', cluster_id='CL0', persona_id='CL0-P0',
                   context_id='CL0-P0-C0', band='core' if i < 2 else 'edge',
                   theta=.8, theta_json=[.8, .2], source='youtube') for i in range(3)],
        codes=[dict(dim='task_goal', code='tg0', label='휴식', count=2)],
        combos=[dict(pair='tg_rc', a_code='tg0', b_code='rc0', count=2)])
    return store


def test_schema_roundtrip_and_version_isolation(layers):
    assert layers.path == version_dir('segment', 'v1') / 'segment/segment.sqlite'
    with sqlite3.connect(layers.path) as db:
        assert {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {
            'docs', 'clusters', 'personas', 'contexts', 'codes', 'combos', 'meta', 'support_docs'}
        assert {'theta_json', 'emerging', 'lexical_surprise', 'pred_entropy'} <= {
            r[1] for r in db.execute('PRAGMA table_info(docs)')}
        assert db.execute('SELECT count FROM codes').fetchone()[0] == 2
        assert db.execute('SELECT count FROM combos').fetchone()[0] == 2
    assert [c['cluster_id'] for c in layers.clusters()] == ['CL0', 'CL2', 'CL10']
    assert layers.clusters()[0]['keywords'] == ['냉방']
    assert len(layers.personas('CL0')) == 1
    assert len(layers.contexts('CL0-P0')) == 2
    np.testing.assert_array_equal(layers.contexts('CL0-P0')[0]['centroid'], np.array([.6, .8], np.float32))
    assert layers.docs('CL0-P0-C0', 'core', limit=1, offset=1)[0]['doc_id'] == 'd1'
    assert layers.docs()[0]['theta'] == .8
    assert layers.docs()[0]['theta_json'] == [.8, .2]
    assert SegmentStore.open('segment', 'v2').clusters() == []
    assert layers.get_run() is None
    layers.set_run('run-one')
    assert SegmentStore.open('segment', 'v1').get_run() == 'run-one'
    assert SegmentStore.open('segment', 'v2').get_run() is None


def test_confirm_last_write_wins_and_preserves_drafts(layers):
    layers.confirm('clusters', 'CL0', {'name': 'first'})
    other = SegmentStore.open('segment', 'v1')
    result = other.confirm('clusters', 'CL0', {'name': 'last'})
    assert result['name'] == 'last'
    assert result['name_draft'] == 'draft 0'
    assert result['confirmed_at']
    result = layers.confirm('personas', 'CL0-P0', {'name': 'p', 'desire': 'd', 'goals': ['g']})
    assert result['desire_draft'] == 'desire draft'
    assert result['goals_draft'] == ['goal draft']
    assert result['goals'] == ['g']
    with pytest.raises((ValueError, StoreError)):
        layers.confirm('clusters', 'CL0', {'name_draft': 'overwritten'})
    layers.add_request('clusters', 'CL0', 'split', '나눠 주세요')
    assert layers.clusters()[0]['requests'][0]['note'] == '나눠 주세요'


def test_confirm_contexts_transaction(layers):
    items = [dict(id='CL0-P0-C0', name='one', action='a'),
             dict(id='CL2-P0-C0', name='wrong parent', action='b')]
    with pytest.raises((ValueError, StoreError)):
        layers.confirm_contexts('CL0-P0', items)
    assert all(c['confirmed_at'] is None for c in layers.contexts())
    # Force a failure after the first UPDATE, testing an actual SQL rollback.
    with sqlite3.connect(layers.path) as db:
        db.execute("""CREATE TRIGGER fail_second BEFORE UPDATE ON contexts
                      WHEN NEW.name = 'fail' BEGIN SELECT RAISE(ABORT, 'injected'); END""")
    items[1] = dict(id='CL0-P0-C1', name='fail', action='b')
    with pytest.raises(sqlite3.IntegrityError):
        layers.confirm_contexts('CL0-P0', items)
    assert all(c['confirmed_at'] is None for c in layers.contexts())
    items[1]['name'] = 'two'
    layers.confirm_contexts('CL0-P0', items)
    assert all(c['confirmed_at'] for c in layers.contexts('CL0-P0'))
    assert layers.contexts('CL2-P0')[0]['confirmed_at'] is None
    assert layers.contexts('CL0-P0')[0]['action_draft'] == 'action draft'


def test_write_layers_atomic_replacement(layers):
    with pytest.raises(sqlite3.IntegrityError):
        layers.write_layers(clusters=[{'cluster_id': 'CL1'}, {'cluster_id': 'CL1'}])
    assert len(layers.clusters()) == 3
    layers.write_layers(clusters=[{'cluster_id': 'CL1'}])
    assert len(layers.clusters()) == 1
    assert layers.docs() == []


def test_docs_filter_by_cluster_persona_and_sort_by_distance(tmp_path):
    from app.segment.store import SegmentStore
    store = SegmentStore(tmp_path)
    rows = [dict(doc_id=f'd{i}', cluster_id='CL1' if i < 4 else 'CL2', persona_id='P1' if i < 2 else 'P2',
                 context_id='C1', dist_centroid=d, band='core') for i, d in enumerate([0.5, 0.1, 0.9, 0.3, 0.2])]
    store.write_layers(docs=rows)
    assert [r['doc_id'] for r in store.docs(cluster_id='CL1', sort='center')] == ['d1', 'd3', 'd0', 'd2']
    assert [r['doc_id'] for r in store.docs(cluster_id='CL1', sort='edge')] == ['d2', 'd0', 'd3', 'd1']
    assert [r['doc_id'] for r in store.docs(persona_id='P1')] == ['d0', 'd1']
    assert [r['doc_id'] for r in store.docs(sort='center', limit=2, offset=1)] == ['d4', 'd3']


def test_support_docs_attach_to_nearest_context(tmp_path):
    import numpy as np
    from types import SimpleNamespace
    from app.segment.pipeline import _assign_support
    from app.segment.store import SegmentStore
    store = SegmentStore(tmp_path)
    store.write_layers(docs=[dict(doc_id='a', cluster_id='CL0', persona_id='P0', context_id='C0'),
                             dict(doc_id='b', cluster_id='CL1', persona_id='P1', context_id='C1')])
    source = SimpleNamespace(index={'a': 0, 'b': 1}, vectors=np.array([[1, 0], [0, 1]], dtype=np.float16),
                             support_ids=['y1', 'y2', 'y3'],
                             support_vectors=np.array([[0.9, 0.1], [0.2, 0.98], [0.6, 0.8]], dtype=np.float16))
    _assign_support(source, store)
    rows, total = store.support_docs(context_id='C1')
    assert total == 2 and [r['doc_id'] for r in rows] == ['y2', 'y3']
    assert [r['doc_id'] for r in store.support_docs(context_id='C1', sort='edge')[0]] == ['y3', 'y2']
    assert store.support_counts() == {'cluster': {'CL0': 1, 'CL1': 2}, 'persona': {'P0': 1, 'P1': 2},
                                      'context': {'C0': 1, 'C1': 2}}
    source.support_ids = []
    _assign_support(source, store)
    assert store.support_counts()['context'] == {}
