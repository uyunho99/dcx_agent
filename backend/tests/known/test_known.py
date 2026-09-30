import json
import sys
from unittest.mock import Mock

import numpy as np
import pytest

from app.config import settings, Settings
from app.context import store
from app.vectors.store import VectorStore


@pytest.fixture
def prepared(data_dir, monkeypatch):
    monkeypatch.setattr(settings, 'embed_backend', 'fake')
    root = data_dir / 'derived/s1/c1/p_123456789abc'
    root.mkdir(parents=True)
    vectors = np.zeros((5, 1024), dtype=np.float32)
    vectors[0, 0] = 1
    vectors[1, 1] = 1
    vectors[2, :2] = [.9, .1]
    vectors[3, 2] = 1
    vectors[4, 3] = 1
    ids = ['statement', 'doc', 'near', 'new', 'non']
    VectorStore(root).write_shard(ids, vectors, [False] * 5)
    docs = [dict(doc_id=i, title=i, desc='sample text', evidence_level_pred='non' if i == 'non' else 'core') for i in ids]
    (root / 'docs').mkdir()
    (root / 'docs/part-00001.jsonl').write_text('\n'.join(map(json.dumps, docs)))
    export = data_dir / 'classified/s1/v1'
    export.mkdir(parents=True)
    (export / 'all.jsonl').write_text('\n'.join(map(json.dumps, docs)))
    (export / 'relevant.jsonl').write_text('\n'.join(map(json.dumps, docs[:-1])))
    store.update_session('s1', dict(schemaVersion=2, sid='s1',
        prep=dict(status='done', derivedRef=dict(collectionId='c1', prepKey='p_123456789abc')),
        training=dict(exportRef='classified/s1/v1/relevant.jsonl')))
    return root, vectors


@pytest.fixture
def search_setup(prepared, monkeypatch):
    from app.known import store as known, filter as search
    embedder = Mock()
    embedder.embed.side_effect = lambda texts: np.repeat(prepared[1][0:1], len(texts), axis=0)
    monkeypatch.setattr(known, 'get_embedder', lambda: embedder)
    monkeypatch.setattr(search, 'get_embedder', lambda: embedder)
    known.add('s1', dict(type='statement', text='already understood'))
    known.add('s1', dict(type='doc', doc_id='doc'))
    return known, search, embedder


def test_statement_and_doc_excluded(search_setup):
    known, search, embedder = search_setup
    assert embedder.embed.call_count == 1
    result = search.search_docs('s1', ['query'], 10)
    assert [d['doc_id'] for d in result.items[0]] == ['new']
    assert result.reason is None


def test_toggle_off_returns_all(search_setup):
    result = search_setup[1].search_docs('s1', ['query'], 10, novel=False)
    assert {d['doc_id'] for d in result.items[0]} == {'statement', 'doc', 'near', 'new'}


def test_theta_similarity_cut(search_setup, monkeypatch):
    search = search_setup[1]
    assert 'near' not in {d['doc_id'] for d in search.search_docs('s1', ['query'], 10).items[0]}
    monkeypatch.setattr(settings, 'known_theta', .999)
    assert 'near' in {d['doc_id'] for d in search.search_docs('s1', ['query'], 10).items[0]}


def test_search_legacy_session_reason(data_dir):
    from app.known.filter import search_docs
    store.update_session('legacy', {'knownInsights': ['old statement']})
    assert search_docs('legacy', ['q'], 5).reason == 'no_vectors'
    from app.known.models import read_known
    assert read_known(store.load_session('legacy'))[0].type == 'statement'


def test_prev_session_statements_copied(client, monkeypatch):
    monkeypatch.setattr(settings, 'embed_backend', 'fake')
    ctx = dict(bk='same', oneLiner='test', researchQuestion={'text': 'why'},
        projectType={'choice': 'new'}, analysisGoal={'choice': 'needs'}, keyMetrics=['m'],
        constraints=[], positioning={'price': 'value', 'market': 'new'}, channels=['fixture'],
        productCategory={'l1': 'a', 'source': 'user'}, knownInsights=['old'])
    previous = client.post('/context', json=ctx).json()['sid']
    from app.known import store as known
    known.add(previous, dict(type='statement', text='another'))
    sid = client.post('/context', json={**ctx, 'knownInsights': ['current']}).json()['sid']
    items = known.list_known(sid)
    assert {i.text for i in items if i.origin == 'prev_session'} == {'old', 'another'}
    assert all(i.vectorRow is not None for i in items)


def test_clustering_reads_store_no_embed_calls(prepared, monkeypatch):
    from app.services import clustering
    embed = Mock(side_effect=AssertionError('must reuse vectors'))
    monkeypatch.setattr(clustering, 'get_embeddings', embed)
    clustering.run_clustering(dict(sid='s1', num_clusters=1))
    assert clustering.job_manager.get('cluster', 's1')['status'] == 'done'
    embed.assert_not_called()


def test_clustering_input_is_core_supporting_only(prepared, monkeypatch):
    from app.services import clustering
    saved = []
    monkeypatch.setattr(clustering, 'save_jsonl', lambda key, docs: saved.extend(docs))
    monkeypatch.setattr(clustering, 'get_embeddings', lambda texts: np.ones((len(texts), 1024)))
    clustering.run_clustering(dict(sid='s1', num_clusters=1))
    assert [d['doc_id'] for d in saved] == ['statement', 'doc', 'near', 'new']


def test_no_pinecone_import():
    import app.main
    assert 'pinecone' not in sys.modules
    assert 'pinecone_api_key' not in Settings.model_fields


def test_final_labels_include_human_review(prepared, search_setup):
    from app.label.store import LabelStore
    from app.label.schema import Tags
    labels = LabelStore(store.session_dir('s1'))
    tags = Tags(anchor=True, sem=dict(sense=1, feel=0, think=0, act=0, relate=0, outcome=0), situation=True)
    with labels._db() as db:
        db.execute('INSERT INTO final VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   ('new', 'core', 1., 'human', 'escalated:human', tags.model_dump_json(), None, None, 'r1', 'q1', '{}', '[]', 0))
    store.update_session('s1', {'training': {'exportRef': None}})
    result = search_setup[1].search_docs('s1', ['q'], 5, novel=False)
    assert [d['doc_id'] for d in result.items[0]] == ['new']


def test_search_reasons_and_query_batch(prepared, search_setup, monkeypatch):
    known, search, embedder = search_setup
    embedder.embed.reset_mock()
    result = search.search_docs('s1', ['one', 'two'], 1, novel=False)
    assert len(result.items) == 2
    embedder.embed.assert_called_once_with(['one', 'two'])
    known.add('s1', dict(type='doc', doc_id='new'))
    assert search.search_docs('s1', ['q'], 5).reason == 'all_known'
    from app.vectors.embedder import EmbedderUnconnected
    monkeypatch.setattr(search, 'get_embedder', Mock(side_effect=EmbedderUnconnected()))
    assert search.search_docs('s1', ['q'], 5).reason == 'embedder_unconnected'
    store.update_session('s1', {'training': {'exportRef': None}})
    assert search.search_docs('s1', ['q'], 5).reason == 'no_labels'


def test_zero_vectors_and_missing_export(prepared, monkeypatch):
    from app.known.filter import search_docs
    from app.services import clustering
    for shard in (prepared[0] / 'vectors').glob('*.f16'):
        shard.write_bytes(bytes(shard.stat().st_size))
    assert search_docs('s1', ['q'], 5).reason == 'no_vectors'
    clustering.run_clustering(dict(sid='s1'))
    assert clustering.job_manager.get('cluster', 's1')['status'] == 'error'
    store.update_session('s1', {'training': {'exportRef': None}})
    fallback = Mock(side_effect=AssertionError('no fallback'))
    monkeypatch.setattr(clustering, 'load_data', fallback)
    clustering.run_clustering(dict(sid='s1'))
    assert clustering.job_manager.get('cluster', 's1')['error'] == '5단계 결과가 없습니다'
    fallback.assert_not_called()


def test_known_api_crud_and_unconnected(client, prepared, monkeypatch):
    monkeypatch.setattr(settings, 'embed_backend', 'voyage')
    response = client.post('/known/s1', json=dict(type='statement', text='known'))
    assert response.status_code == 201
    item = response.json()
    assert item['vectorRow'] is None and item['warning']
    assert client.patch('/known/s1/' + item['id'], json={'text': ''}).status_code == 422
    monkeypatch.setattr(settings, 'embed_backend', 'fake')
    item = client.patch('/known/s1/' + item['id'], json={'text': 'changed'}).json()
    assert item['vectorRow'] == 0
    assert client.get('/known/s1').json()['items'][0]['text'] == 'changed'
    assert client.delete('/known/s1/' + item['id']).status_code == 200
    assert client.get('/known/s1').json() == {'items': []}
    assert client.post('/known/s1', json=dict(type='doc', doc_id='missing')).status_code == 404


def test_known_versions_and_statement_embedding_once(search_setup, monkeypatch):
    from app.context import versions
    known, search, embedder = search_setup
    item = known.list_known('s1')[0]
    before = embedder.embed.call_count
    known.update('s1', item.id, {'text': item.text})
    assert embedder.embed.call_count == before
    versions.create_version('s1', 'v1', 'stage4', '')
    assert (store.session_dir('s1') / 'known_vectors.f16').exists()
    known.delete('s1', item.id)
    versions.create_version('s1', 'v1', 'stage4', '')
    assert item.id in {i.id for i in known.list_known('s1')}


def test_callers_novel_and_sources(client, search_setup, monkeypatch):
    from app.routers import chat
    monkeypatch.setattr(chat, 'call_claude', lambda *args, **kwargs: 'answer')
    for path in ('/chat', '/insight-chat', '/search'):
        response = client.post(path, json={'sid': 's1', 'query': 'q', 'novel': False}).json()
        items = response['results' if path == '/search' else 'sources']
        assert {d['doc_id'] for d in items} == {'statement', 'doc', 'near', 'new'}
        response = client.post(path, json={'sid': 's1', 'query': 'q'}).json()
        assert [d['doc_id'] for d in response['results' if path == '/search' else 'sources']] == ['new']


def test_personas_queries_batched(search_setup, monkeypatch):
    from app.services import personas
    from app.known.filter import SearchResult
    search = Mock(return_value=SearchResult([[], []], 'all_known'))
    monkeypatch.setattr(personas, 'search_docs', search)
    monkeypatch.setattr(personas, 'load_data', lambda key: [dict(cluster=i, kw=str(i), title='EXCLUDED', desc='EXCLUDED') for i in range(2)])
    monkeypatch.setattr(personas, 'load_json', lambda key: None)
    monkeypatch.setattr(personas, 'save_json', lambda *args: None)
    llm = Mock(return_value='[]')
    monkeypatch.setattr(personas, 'call_claude', llm)
    personas.run_persona({'sid': 's1'})
    search.assert_called_once_with('s1', ['0', '1'], top_k=10, novel=True)
    assert 'EXCLUDED' not in llm.call_args.args[0]


def test_embedding_immediately_done(prepared, monkeypatch):
    from app.services.embedding import run_embedding
    from app.jobs.manager import job_manager
    run_embedding({'sid': 's1'})
    job = job_manager.get('embed', 's1')
    assert job['status'] == 'done' and job['message'] == '3단계 벡터 사용'


def test_search_uses_preparation_embedder(prepared, monkeypatch):
    from app.known.filter import search_docs
    store.write_json(prepared[0] / 'manifest.json', {'embedder': {'name': 'fake', 'model': 'voyage-4', 'dim': 1024}})
    monkeypatch.setattr(settings, 'embed_backend', 'voyage')
    result = search_docs('s1', ['q'], 5, novel=False)
    assert result.reason is None and result.items[0]


def test_retry_unconnected_statement_on_patch(prepared, monkeypatch):
    from app.known import store as known
    monkeypatch.setattr(settings, 'embed_backend', 'voyage')
    item = known.add('s1', dict(type='statement', text='known'))
    assert item.vectorRow is None
    monkeypatch.setattr(settings, 'embed_backend', 'fake')
    assert known.update('s1', item.id, {'text': 'known'}).vectorRow == 0


def test_statement_survives_embedding_failure(prepared, monkeypatch):
    from app.known import store as known
    failed = Mock()
    failed.embed.side_effect = ValueError('provider failure')
    monkeypatch.setattr(known, 'get_embedder', lambda: failed)
    item = known.add('s1', dict(type='statement', text='keep this'))
    assert item.vectorRow is None
    assert known.list_known('s1')[0].text == 'keep this'


def test_clustering_follows_inherited_export_ref(prepared, monkeypatch):
    from app.context import versions
    from app.services import clustering
    versions.create_version('s1', 'v1', 'stage6', '')
    embed = Mock(side_effect=AssertionError('must reuse vectors'))
    monkeypatch.setattr(clustering, 'get_embeddings', embed)
    clustering.run_clustering({'sid': 's1', 'num_clusters': 1})
    assert clustering.job_manager.get('cluster', 's1')['status'] == 'done'
    embed.assert_not_called()


@pytest.fixture
def persona_prompt(monkeypatch):
    from app.services import personas
    monkeypatch.setattr(personas, 'load_json', lambda key: None)
    monkeypatch.setattr(personas, 'save_json', lambda *args: None)
    llm = Mock(return_value='[]')
    monkeypatch.setattr(personas, 'call_claude', llm)
    return personas, llm


@pytest.mark.parametrize('reason', ['no_vectors', 'no_labels', 'embedder_unconnected', 'all_known'])
def test_persona_fallback_reasons_and_known_exclusion(data_dir, persona_prompt, monkeypatch, reason):
    from app.known.filter import SearchResult
    personas, llm = persona_prompt
    store.update_session('legacy', {'knownInsights': [dict(type='doc', doc_id='known', text='known')]})
    docs = [dict(cluster=0, kw='query', doc_id='known', title='KNOWN_TITLE')]
    docs += [dict(cluster=0, kw='query', doc_id=str(i), title=f'EVIDENCE_{i}_END') for i in range(21)]
    monkeypatch.setattr(personas, 'load_data', lambda key: docs)
    # The legacy case exercises real search with no derivedRef.
    if reason != 'no_vectors':
        monkeypatch.setattr(personas, 'search_docs', Mock(return_value=SearchResult([[]], reason)))
    personas.run_persona({'sid': 'legacy'})
    assert personas.job_manager.get('persona', 'legacy')['status'] == 'done'
    prompt = llm.call_args.args[0]
    assert ('EVIDENCE_0_END' in prompt) == (reason != 'all_known')
    assert 'KNOWN_TITLE' not in prompt
    assert 'EVIDENCE_19_END' not in prompt  # Slice raw cluster to 20 before filtering.


@pytest.mark.parametrize('all_empty', [False, True])
def test_persona_skips_empty_queries(data_dir, persona_prompt, monkeypatch, all_empty):
    from app.known.filter import SearchResult
    personas, llm = persona_prompt
    docs = [dict(cluster=0, title='EMPTY_QUERY_EVIDENCE', kw='  '),
            dict(cluster=1, title='SECOND_CLUSTER', kw='' if all_empty else 'query')]
    monkeypatch.setattr(personas, 'load_data', lambda key: docs)
    search = Mock(return_value=SearchResult([[dict(title='RAG_EVIDENCE')]]))
    monkeypatch.setattr(personas, 'search_docs', search)
    personas.run_persona({'sid': 's1'})
    assert personas.job_manager.get('persona', 's1')['status'] == 'done'
    prompt = llm.call_args.args[0]
    assert 'EMPTY_QUERY_EVIDENCE' in prompt
    if all_empty:
        search.assert_not_called()
        assert 'SECOND_CLUSTER' in prompt
    else:
        search.assert_called_once_with('s1', ['query'], top_k=10, novel=True)
        assert 'RAG_EVIDENCE' in prompt.split('### 클러스터 2')[1]


def test_search_releases_lock_before_embedding_and_scans(prepared, monkeypatch):
    import fcntl
    from app.known import filter as search

    def assert_unlocked():
        with (store.root_dir('s1') / '.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(lock, fcntl.LOCK_UN)

    embedder = Mock()
    def embed(texts):
        assert_unlocked()
        return prepared[1][:len(texts)]
    embedder.embed.side_effect = embed
    monkeypatch.setattr(search, 'get_embedder', lambda: embedder)
    original_docs = search.relevant_documents
    def read_docs(*args, **kwargs):
        assert_unlocked()
        return original_docs(*args, **kwargs)
    monkeypatch.setattr(search, 'relevant_documents', read_docs)
    original_scan = VectorStore.iter_shards
    scans = []
    def scan(self):
        assert_unlocked()
        scans.append(True)
        yield from original_scan(self)
    monkeypatch.setattr(VectorStore, 'iter_shards', scan)
    result = search.search_docs('s1', ['q'], 5)
    assert result.items[0]
    embedder.embed.assert_called_once_with(['q'])
    assert len(scans) == 1


@pytest.mark.parametrize('ref', ['classified/s1/missing/relevant.jsonl',
                                  'classified/s1/v1/all.jsonl',
                                  'classified/other/v1/relevant.jsonl'])
def test_invalid_export_returns_no_labels(client, prepared, ref):
    from app.known.filter import search_docs
    store.update_session('s1', {'training': {'exportRef': ref}})
    result = search_docs('s1', ['q', 'q2'], 5)
    assert result.reason == 'no_labels' and result.items == [[], []]
    response = client.post('/search', json={'sid': 's1', 'query': 'q'})
    assert response.status_code == 200
    assert response.json()['reason'] == 'no_labels'


def test_initialize_batches_missing_statement_vectors(prepared, monkeypatch):
    from app.known import store as known
    store.update_session('s1', {'bk': 'same', 'knownInsights': ['first', 'second']})
    store.update_session('previous', {'bk': 'same', 'knownInsights': ['second', 'copied']})
    embedder = Mock()
    embedder.embed.return_value = prepared[1][:3]
    monkeypatch.setattr(known, 'get_embedder', lambda: embedder)
    known.initialize('s1')
    embedder.embed.assert_called_once_with(['first', 'second', 'copied'])
    items = known.list_known('s1')
    assert [item.vectorRow for item in items] == [0, 1, 2]
    np.testing.assert_allclose(known.known_vectors('s1', items, VectorStore(prepared[0])),
                               prepared[1][:3], atol=.001)
    known.initialize('s1')
    assert embedder.embed.call_count == 1
