"""Offline STEP 09 contracts, using golden inputs and mocked Pinecone."""
from copy import deepcopy
from unittest.mock import Mock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.services import evidence, pinecone_svc, s3
from app.routers.evidence import router


@pytest.fixture
def inputs(golden_classified, golden_clusters, golden_personas, golden_evidence):
    source = golden_classified()
    return dict(sid=source['sid'], persona=golden_personas()['personas'][0],
                cluster=golden_clusters()['clusters'][0], records=source['records'],
                actions=golden_evidence()['actions'], known_insights=source['known_insights'])


@pytest.fixture
def retrieval(monkeypatch, golden_evidence):
    monkeypatch.setattr(pinecone_svc, 'update_context_mappings', Mock())
    rows = golden_evidence()['evidence']
    def search(sid, query, top_k=50, *, filters):
        return [dict(r, score=r['relevance']) for r in rows
                if all(r[k] == v for k, v in filters.items())]
    mock = Mock(side_effect=search)
    monkeypatch.setattr(pinecone_svc, 'search_similar', mock)
    return mock


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_golden_scores_ranks_and_centroid(inputs, retrieval, golden_evidence):
    result = evidence.build_package(**inputs)
    expected = golden_evidence()
    for field in ('centroid_sentence', 'coverage', 'actions', 'warnings'):
        assert result[field] == expected[field]
    for actual, wanted in zip(result['evidence'], expected['evidence'], strict=True):
        for field in ('doc_id', 'quote', 'dims', 'band', 'role', 'action_id', 'context_id'):
            assert actual[field] == wanted[field]
        for field in ('relevance', 'known', 'rarity', 'quality', 'max_sim_to_known', 'combo_rarity'):
            assert actual[field] == pytest.approx(wanted[field])
        assert actual['relevance_rank'] == actual['rank_relevance'] == wanted['rank_relevance']
        assert actual['quality_rank'] == actual['rank_quality'] == wanted['rank_quality']
    assert any(r['quality_rank'] != r['relevance_rank'] for r in result['evidence'])
    assert retrieval.call_count == 2


def test_empty_known_disables_both_adjustments(inputs, retrieval, caplog):
    inputs['known_insights'] = []
    result = evidence.build_package(**inputs)
    assert result['warnings'] == ['KNOWN_INSIGHTS_EMPTY']
    assert 'KNOWN_INSIGHTS_EMPTY' in caplog.text
    assert any(r['rarity'] > 0 for r in result['evidence'])
    assert all(r['known'] == r['max_sim_to_known'] == 0 and r['quality'] == r['relevance']
               for r in result['evidence'])


def test_centroid_text_duplicate_and_action_membership(inputs, monkeypatch, golden_evidence):
    rows = golden_evidence()['evidence']
    centroid = golden_evidence()['centroid_sentence']
    rows[0]['quote'] = centroid['text']
    inputs['actions'][0]['doc_ids'].append(centroid['doc_id'])
    monkeypatch.setattr(pinecone_svc, 'search_similar', lambda *a, **kw: [
        r for r in rows if r['context_id'] == kw['filters']['context_id']])
    result = evidence.build_package(**inputs)
    assert all(r['quote'] != centroid['text'] for r in result['evidence'])
    assert all(centroid['doc_id'] not in a['doc_ids'] for a in result['actions'])


@pytest.mark.parametrize('count,expected_calls', [(0, 1), (3, 1), (4, 0), (6, 0)])
def test_coverage_boundary(inputs, monkeypatch, golden_evidence, count, expected_calls):
    rows = golden_evidence()['evidence']
    for r in rows:
        r['dims'] = list(evidence.DIMENSIONS)[:count]
    monkeypatch.setattr(pinecone_svc, 'search_similar', lambda *a, **kw: [
        r for r in rows if r['context_id'] == kw['filters']['context_id']])
    supplement = Mock(return_value=golden_evidence()['evidence'])
    monkeypatch.setattr(evidence, 'supplement_search', supplement)
    result = evidence.build_package(**inputs)
    assert supplement.call_count == expected_calls
    if expected_calls:
        assert len(result['coverage']['dims']) == 6
    assert len({r['doc_id'] for r in result['evidence']}) == len(result['evidence'])


def seed(inputs, monkeypatch):
    sid = inputs['sid']
    s3.save_json(f'sessions/{sid}/session.json', {'known_insights': inputs['known_insights']})
    s3.save_json(f'personas/{sid}/result_1.json', {'personas': [inputs['persona']]})
    s3.save_json(f'clusters/{sid}/result_1.json', {'clusters': [inputs['cluster']]})
    s3.save_jsonl(f'classified/{sid}/relevant_1.jsonl', inputs['records'])
    monkeypatch.setattr(evidence, 'derive_actions', lambda *args: deepcopy(inputs['actions']))


def test_collect_storage_and_get_sort(inputs, retrieval, monkeypatch, client):
    seed(inputs, monkeypatch)
    response = client.post('/api/evidence/collect', json={'sid': inputs['sid'], 'persona_id': 'CL0-P1'})
    assert response.status_code == 202
    job = client.get('/api/evidence/status/golden-a/CL0-P1').json()
    assert job['status'] == 'done' and job['progress'] == 100
    stored = s3.load_json(job['key'])
    assert stored['actions'] and stored['centroid_sentence']
    response = client.get('/api/evidence/golden-a/CL0-P1?sort_by=relevance')
    assert response.status_code == 200
    rows = response.json()['evidence']
    assert [r['relevance_rank'] for r in rows] == list(range(1, len(rows) + 1))
    assert {r['doc_id']: r['quality_rank'] for r in rows} == {
        r['doc_id']: r['quality_rank'] for r in stored['evidence']}


def test_collect_syncs_derived_document_contexts_before_search(inputs, monkeypatch):
    source = {k: v for k, v in inputs.items() if k != 'actions'}
    monkeypatch.setattr(evidence, 'load_inputs', lambda *args: source)
    actions = evidence.derive_actions(source['persona'], source['cluster'], source['records'])
    expected = [dict(doc_id=doc_id, cluster_id=source['persona']['cluster_id'],
                     persona_id=source['persona']['persona_id'], context_id=action['context_id'])
                for action in actions for doc_id in action['doc_ids']]
    mappings = []
    events = []
    records = {r['doc_id']: r for r in source['records']}

    def update(sid, rows):
        assert sid == source['sid']
        events.append(('update', deepcopy(rows)))
        mappings[:] = deepcopy(rows)

    def search(sid, query, top_k=50, *, filters):
        events.append(('search', dict(filters)))
        return [dict(row, quote=records[row['doc_id']]['text'], score=.8,
                     max_sim_to_known=.2, combo_rarity=.3, dims=list(evidence.DIMENSIONS))
                for row in mappings if all(row[k] == v for k, v in filters.items())]

    monkeypatch.setattr(pinecone_svc, 'update_context_mappings', update)
    monkeypatch.setattr(pinecone_svc, 'search_similar', search)
    key = evidence.collect(source['sid'], source['persona']['persona_id'])
    assert events[0] == ('update', expected), 'Document-context mapping must be synced before search'
    assert [kind for kind, _ in events] == ['update'] + ['search'] * len(actions)
    stored = s3.load_json(key)
    assert {r['doc_id']: r['context_id'] for r in stored['evidence']} == {
        r['doc_id']: r['context_id'] for r in expected}


@pytest.mark.parametrize('implemented', [False, True])
def test_collect_mapping_failure_prevents_search_and_save(inputs, monkeypatch, implemented):
    source = {k: v for k, v in inputs.items() if k != 'actions'}
    monkeypatch.setattr(evidence, 'load_inputs', lambda *args: source)
    if implemented:
        monkeypatch.setattr(pinecone_svc, 'update_context_mappings',
                            Mock(side_effect=RuntimeError('metadata update failed')))
    search = Mock()
    save = Mock()
    monkeypatch.setattr(pinecone_svc, 'search_similar', search)
    monkeypatch.setattr(s3, 'save_json', save)
    with pytest.raises(evidence.RetrievalUnavailable, match='mapping sync unavailable') as exc:
        evidence.collect(source['sid'], source['persona']['persona_id'])
    assert isinstance(exc.value.__cause__, RuntimeError if implemented else NotImplementedError)
    search.assert_not_called()
    save.assert_not_called()


@pytest.mark.parametrize('missing', ['cluster_id', 'persona_id', 'context_id', 'all'])
def test_search_requires_all_three_filters(client, monkeypatch, missing):
    mock = Mock()
    monkeypatch.setattr(pinecone_svc, 'search_similar', mock)
    filters = dict(cluster_id='CL0', persona_id='CL0-P1', context_id='CL0-P1-C1')
    if missing == 'all':
        filters = {}
    else:
        del filters[missing]
    response = client.post('/api/evidence/search', json={'sid': 'golden-a', 'query': 'watch', 'filters': filters})
    assert response.status_code == 422
    mock.assert_not_called()


@pytest.mark.parametrize('value', ['', '   ', None])
def test_search_rejects_empty_filter_values(client, value):
    response = client.post('/api/evidence/search', json={'sid': 'golden-a', 'query': 'watch',
        'filters': {'cluster_id': value, 'persona_id': 'CL0-P1', 'context_id': 'CL0-P1-C1'}})
    assert response.status_code == 422


def test_search_scoped_and_relevance_sort(inputs, retrieval, monkeypatch, client):
    seed(inputs, monkeypatch)
    evidence.collect(inputs['sid'], 'CL0-P1')
    filters = dict(cluster_id='CL0', persona_id='CL0-P1', context_id='CL0-P1-C1')
    response = client.post('/api/evidence/search', json={'sid': inputs['sid'], 'query': 'watch',
                                                        'filters': filters, 'sort_by': 'relevance'})
    assert response.status_code == 200
    rows = response.json()['evidence']
    assert rows
    assert all(all(r[k] == v for k, v in filters.items()) for r in rows)
    assert [r['relevance_rank'] for r in rows] == list(range(1, len(rows) + 1))
    assert retrieval.call_args.kwargs['filters'] == filters


def test_pinecone_failure_propagates_and_http_refuses(inputs, retrieval, monkeypatch, client):
    seed(inputs, monkeypatch)
    evidence.collect(inputs['sid'], 'CL0-P1')
    retrieval.side_effect = RuntimeError('index missing')
    with pytest.raises(evidence.RetrievalUnavailable, match='05'):
        evidence.build_package(**inputs)
    response = client.post('/api/evidence/search', json={'sid': inputs['sid'], 'query': 'watch',
        'filters': dict(cluster_id='CL0', persona_id='CL0-P1', context_id='CL0-P1-C1')})
    assert response.status_code == 503
    assert '05' in response.json()['detail']
    client.post('/api/evidence/collect', json={'sid': inputs['sid'], 'persona_id': 'CL0-P1'})
    assert client.get('/api/evidence/status/golden-a/CL0-P1').json()['status'] == 'error'


def test_scope_leak_is_rejected(inputs, retrieval):
    retrieval.side_effect = None
    retrieval.return_value = [dict(doc_id='foreign', cluster_id='CL9', persona_id='CL9-P1', context_id='CL9-P1-C1')]
    with pytest.raises(evidence.RetrievalUnavailable):
        evidence.build_package(**inputs)


def test_supplement_uses_same_required_filters(inputs, retrieval):
    evidence.supplement_search(inputs['sid'], inputs['persona'], inputs['actions'], ['Sense'])
    assert retrieval.call_count == len(inputs['actions'])
    assert all(set(c.kwargs['filters']) == {'cluster_id', 'persona_id', 'context_id'}
               for c in retrieval.call_args_list)


def test_session_b_golden(golden_classified, golden_clusters, golden_personas, golden_evidence, monkeypatch):
    source = golden_classified('b')
    expected = golden_evidence(session='b')
    monkeypatch.setattr(pinecone_svc, 'search_similar', lambda *args, **kw: [
        row for row in expected['evidence'] if row['context_id'] == kw['filters']['context_id']])
    result = evidence.build_package(sid=source['sid'], persona=golden_personas('b')['personas'][0],
        cluster=golden_clusters('b')['clusters'][0], records=source['records'],
        actions=expected['actions'], known_insights=source['known_insights'])
    assert result['warnings'] == expected['warnings']
    for row, wanted in zip(result['evidence'], expected['evidence'], strict=True):
        assert row['doc_id'] == wanted['doc_id']
        assert row['quality'] == wanted['relevance']
        assert row['known'] == 0
        assert row['rarity'] == wanted['rarity']


def test_lda_actions_are_deterministic_and_grounded(inputs):
    args = (inputs['persona'], inputs['cluster'], inputs['records'])
    actions = evidence.derive_actions(*args)
    assert actions == evidence.derive_actions(*args)
    centroid = evidence.centroid_sentence(*args)
    ids = [doc_id for a in actions for doc_id in a['doc_ids']]
    assert len(ids) == len(set(ids))
    assert set(ids) == set(inputs['persona']['doc_ids']) - {centroid['doc_id']}
    records = {r['doc_id']: r for r in inputs['records']}
    assert sum(a['topic_weight'] for a in actions) == pytest.approx(1)
    for a in actions:
        assert a['docs'] == len(a['doc_ids'])
        assert a['sentence'] in [records[d]['text'] for d in a['doc_ids']]


def test_rank_ties_are_doc_id_order_and_quality_not_clamped(inputs, retrieval):
    retrieval.side_effect = None
    retrieval.return_value = []
    assert evidence.quality_score(1, 0, 1, True) == 1.3
    rows = [dict(doc_id='d2', relevance=.5, quality=.6), dict(doc_id='d1', relevance=.5, quality=.6)]
    result = evidence._rank(rows, 'quality')
    assert [r['doc_id'] for r in result] == ['d1', 'd2']
    assert all(r['relevance_rank'] == r['quality_rank'] for r in result)


def test_unfilled_coverage_is_explicit_and_empty_search_is_bounded(inputs, retrieval):
    retrieval.side_effect = None
    retrieval.return_value = []
    result = evidence.build_package(**inputs)
    assert result['evidence'] == []
    assert result['coverage'] == {'dims': [], 'min': 4}
    assert result['warnings'] == ['COVERAGE_BELOW_MIN']
    assert retrieval.call_count == 2 * len(inputs['actions'])


def test_supplement_failure_is_not_swallowed(inputs, retrieval, monkeypatch):
    retrieval.side_effect = None
    retrieval.return_value = []
    monkeypatch.setattr(evidence, 'supplement_search', Mock(side_effect=evidence.RetrievalUnavailable('unavailable')))
    with pytest.raises(evidence.RetrievalUnavailable):
        evidence.build_package(**inputs)


def test_unknown_context_rejected_before_retrieval(inputs, retrieval, monkeypatch, client):
    seed(inputs, monkeypatch)
    evidence.collect(inputs['sid'], 'CL0-P1')
    retrieval.reset_mock()
    response = client.post('/api/evidence/search', json={'sid': inputs['sid'], 'query': 'watch',
        'filters': dict(cluster_id='CL0', persona_id='CL0-P1', context_id='CL0-P1-C99')})
    assert response.status_code == 422
    retrieval.assert_not_called()


def test_latest_classified_run_excludes_sidecars_and_old_runs(inputs, monkeypatch):
    seed(inputs, monkeypatch)
    sid = inputs['sid']
    s3.save_jsonl(f'classified/{sid}/relevant_0.jsonl', [{'doc_id': 'obsolete'}])
    s3.save_json(f'classified/{sid}/run_2.json', {'counts': {}})
    assert evidence.load_inputs(sid, 'CL0-P1')['records'] == inputs['records']
