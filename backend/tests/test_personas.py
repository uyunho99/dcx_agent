import copy
import math
from unittest.mock import Mock

import numpy as np
import pytest

from app.jobs.manager import job_manager
from app.services import personas, s3
from app.routers import personas as router

@pytest.fixture(autouse=True)
def no_external_calls(monkeypatch):
    monkeypatch.setattr(personas, 'call_claude', Mock(return_value='[]'), raising=False)
    monkeypatch.setattr(personas, 'search_similar', Mock(return_value=[]), raising=False)


FIELDS = {'persona_id', 'desire', 'goals', 'centrality_top', 'modularity_q', 'status'}


def seed(clusters, records):
    sid = clusters['sid']
    s3.save_json(f'clusters/{sid}/result_20260918_120000.json', clusters)
    s3.save_jsonl(f'classified/{sid}/relevant_20260918_120000.jsonl', records)
    return sid


def result(sid):
    personas.run_persona({'sid': sid})
    job = job_manager.get('persona', sid)
    assert job['status'] == 'done', job
    keys = s3.list_objects(f'personas/{sid}/')
    return s3.load_json(sorted(x['Key'] for x in keys)[-1])


@pytest.mark.parametrize('session', ['a', 'b'])
def test_golden_v2(golden_clusters, golden_classified, session):
    clusters = golden_clusters(session)
    records = golden_classified(session)['records']
    data = result(seed(clusters, records))
    assert data['schema_version'] == 2
    assert data['sid'] == clusters['sid']
    assert len(data['personas']) == 3
    for p, c in zip(data['personas'], clusters['clusters']):
        assert set(p) == FIELDS
        assert p['persona_id'] == c['cluster_id'] + '-P1'
        assert p['desire'] and p['goals']
        assert p['status'] == 'draft'
        assert p['modularity_q'] == pytest.approx(0)
        assert {x[0] for x in p['centrality_top']} == {x[0] for x in c['c_tfidf']}
        assert [x[1] for x in p['centrality_top']] == pytest.approx([1 / math.sqrt(3)] * 3)
    graph = router.get_sna_data(clusters['sid'])
    assert graph['status'] == 'ok'
    assert len([n for n in graph['nodes'] if n['type'] == 'persona']) == 3


def test_weighted_cooccurrence_and_eigenvector():
    terms, matrix = personas.cooccurrence_matrix([
        {'keywords': ['a', 'b', 'b']}, {'keywords': ['a', 'b']},
        {'keywords': ['b', 'c']},
    ])
    assert terms == ['a', 'b', 'c']
    np.testing.assert_array_equal(matrix, [[0, 2, 0], [2, 0, 1], [0, 1, 0]])
    scores = personas.eigenvector_centrality(matrix)
    np.testing.assert_allclose(matrix @ scores, math.sqrt(5) * scores, atol=1e-8)
    assert np.linalg.norm(scores) == pytest.approx(1)


def test_modularity_splits_connected_groups_without_crossing_clusters():
    records = []
    clusters = []
    for cid in ['CL0', 'CL1']:
        docs = []
        for i, words in enumerate([['a', 'b', 'c']] * 4 + [['d', 'e', 'f']] * 4 + [['c', 'd']]):
            doc_id = f'{cid}_{i}'
            docs.append({'doc_id': doc_id})
            records.append({'doc_id': doc_id, 'keywords': words})
        clusters.append({'cluster_id': cid, 'documents': docs})
    output = personas.generate_personas(clusters, records)
    assert [p['persona_id'] for p in output] == ['CL0-P1', 'CL0-P2', 'CL1-P1', 'CL1-P2']
    for p in output:
        assert p['modularity_q'] == pytest.approx(.46)
        assert {t for t, _ in p['centrality_top']} in ({'a', 'b', 'c'}, {'d', 'e', 'f'})
    baseline = copy.deepcopy(output[:2])
    for r in records[9:]:
        r['keywords'] = ['foreign', 'only']
    assert personas.generate_personas(clusters, records)[:2] == baseline


@pytest.mark.parametrize('fault', ['duplicate_membership', 'missing_document', 'duplicate_cluster', 'invalid_id'])
def test_invalid_cluster_scope_is_rejected(golden_clusters, golden_classified, fault):
    clusters = golden_clusters()
    records = golden_classified()['records']
    if fault == 'duplicate_membership':
        clusters['clusters'][1]['documents'].append(clusters['clusters'][0]['documents'][0])
    elif fault == 'missing_document':
        records.pop(0)
    elif fault == 'duplicate_cluster':
        clusters['clusters'][1]['cluster_id'] = 'CL0'
    else:
        clusters['clusters'][0]['cluster_id'] = '0'
    sid = seed(clusters, records)
    personas.run_persona({'sid': sid})
    assert job_manager.get('persona', sid)['status'] == 'error'
    assert not s3.list_objects(f'personas/{sid}/')


@pytest.mark.parametrize('keywords', [[], ['alone']])
def test_sparse_graphs_are_finite_and_explicit(keywords):
    output = personas.generate_personas(
        [{'cluster_id': 'CL0', 'documents': [{'doc_id': 'd1'}]}],
        [{'doc_id': 'd1', 'keywords': keywords}],
    )
    assert len(output) == 1
    assert output[0]['modularity_q'] == 0
    assert output[0]['status'] == ('draft' if keywords else 'insufficient_data')
    assert output[0]['centrality_top'] == ([['alone', 1.0]] if keywords else [])


@pytest.mark.parametrize('cid', [1, 'CL0', None])
def test_v1_read_only(cid, local_data_dir):
    sid = f'legacy-{cid}'
    legacy = {'personas': [{'cluster_id': cid, 'personas': [{'name': 'legacy', 'situation': 'old'}]}]}
    key = f'personas/{sid}/result_20250101_000000.json'
    s3.save_json(key, legacy)
    before = (local_data_dir / key).read_bytes()
    assert router.get_persona_status(sid)['personas'] == legacy['personas']
    assert router.get_sna_data(sid)['status'] == 'ok'
    assert (local_data_dir / key).read_bytes() == before


def test_latest_snapshot_only(golden_clusters, golden_classified):
    clusters = golden_clusters()
    records = golden_classified()['records']
    sid = seed(clusters, records)
    s3.save_json(f'clusters/{sid}/result_20200101_000000.json', {'clusters': []})
    s3.save_jsonl(f'classified/{sid}/relevant_20200101_000000.jsonl', [{'doc_id': records[0]['doc_id'], 'keywords': ['stale']}])
    s3.save_json(f'clusters/{sid}/zzz_metadata.json', {})
    assert len(result(sid)['personas']) == 3


def test_post_plural_route():
    assert any(r.path == '/personas' and 'POST' in r.methods for r in router.router.routes)


def test_disconnected_eigenvector_is_deterministic():
    adjacency = np.array([[0, 1, 0, 0], [1, 0, 0, 0],
                          [0, 0, 0, 1], [0, 0, 1, 0]], dtype=float)
    scores = personas.eigenvector_centrality(adjacency)
    np.testing.assert_allclose(scores, [.5] * 4)
    groups, q = personas.modularity_partition(adjacency)
    assert groups == [[0, 1], [2, 3]]
    assert q == pytest.approx(.5)


def test_s3_uses_latest_exact_source_key(monkeypatch, golden_clusters, golden_classified):
    artifact = golden_clusters()
    sid = artifact['sid']
    cluster_key = f'clusters/{sid}/result_20260918_120000.json'
    source_key = f'classified/{sid}/relevant_20260918_120000.jsonl'
    monkeypatch.setattr(s3, '_USE_LOCAL', False)
    monkeypatch.setattr(personas, 'list_objects', lambda prefix: [
        {'Key': key} for key in [cluster_key, source_key] if key.startswith(prefix)])
    monkeypatch.setattr(personas, 'load_json', lambda key: artifact)
    source = Mock(return_value=golden_classified()['records'])
    saved = Mock()
    monkeypatch.setattr(personas, 'load_data', source)
    monkeypatch.setattr(personas, 'save_json', saved)
    personas.run_persona({'sid': sid})
    assert job_manager.get('persona', sid)['status'] == 'done'
    source.assert_called_once_with(source_key)
    assert saved.call_args.args[1]['schema_version'] == 2


def test_v2_reload_excludes_unrelated_files(golden_personas):
    saved = golden_personas()
    sid = 'reloaded'
    s3.save_json(f'personas/{sid}/result_20260918_120000.json', saved)
    s3.save_json(f'personas/{sid}/zzz_metadata.json', {'personas': []})
    response = router.get_persona_status(sid)
    assert response['schema_version'] == 2
    assert response['personas'] == saved['personas']
    graph = router.get_sna_data(sid)
    assert graph['status'] == 'ok'
    for node in graph['nodes']:
        assert not {'situation', 'pain_point', 'insight'} & node.keys()
