import json
import re

import numpy as np
import pytest
from pydantic import BaseModel

from app.config import settings
from app.context import store as sessions
from app.llm.base import LLMTask
from app.llm.fake import FakeBackend
from app.model.infer import prepared_root
from app.segment.inputs import load_input
from app.segment.store import SegmentStore
from app.vectors.store import VectorStore
from tests.fixtures.evidence_synth import (
    QueryEmbedder, fake_evidence_backend, make_evidence_session,
)


@pytest.fixture
def ready(data_dir):
    return make_evidence_session(data_dir, docs_per_context=4)


def test_session_ready_for_stage7(data_dir):
    before = (settings.local_data_dir, settings.embed_backend, settings.llm_backend)
    fixture = make_evidence_session(data_dir / 'isolated', docs_per_context=4)
    assert (settings.local_data_dir, settings.embed_backend, settings.llm_backend) == before
    root = data_dir / 'isolated' / 'sessions' / fixture.sid / 'versions' / fixture.version
    state = sessions.read_json(root / 'session.json')
    assert state['segment']['status'] == 'done'
    assert state['completion']['segmentDone'] is True
    store = SegmentStore(root)
    for layer, key in [('clusters', 'cluster_id'), ('personas', 'persona_id'), ('contexts', 'context_id')]:
        rows = getattr(store, layer)()
        assert rows and all(row['confirmed_at'] for row in rows)
        assert state['segment']['confirm'][layer] == f'{len(rows)}/{len(rows)}'
        assert all(row['name'] == (row['name_draft'] or f"{row[key].split('-')[0]} 이름") for row in rows)
    assert all(p['desire'] == p['desire_draft'] and p['goals'] == p['goals_draft'] for p in store.personas())
    assert all(c['action'] == c['action_draft'] for c in store.contexts())


def test_query_embedder_points_to_context(ready):
    state = sessions.load_session(ready.sid)
    vectors = VectorStore(prepared_root(ready.sid, state))
    embedder = QueryEmbedder(ready, vectors)
    for layer, words_key in [('context', 'context_tokens'), ('persona', 'persona_nouns')]:
        directions = []
        vocabulary = ready.expected[words_key]
        for owner in vocabulary:
            ids = [doc_id for doc_id, assignment in ready.expected['assignments'].items()
                   if assignment[layer] == owner and doc_id not in ready.expected['no_token_ids']]
            _, values = vectors.get(ids)
            values = values[np.linalg.norm(values, axis=1) > 0]
            center = values.mean(axis=0)
            directions.append(center / np.linalg.norm(center))
        queries = [f'나는 {words[0]} 경험을 찾고 싶다.' for words in vocabulary.values()]
        result = embedder.embed(queries, input_type='query')
        assert result.dtype == np.float32
        np.testing.assert_allclose(result, directions, atol=1e-6)
        assert np.array_equal(np.argmax(result @ np.asarray(directions).T, axis=1), np.arange(len(queries)))
    fallback = embedder.embed(['unknown sentence'])
    np.testing.assert_array_equal(fallback, QueryEmbedder(ready, vectors).embed(['unknown sentence'], input_type='query'))
    assert np.linalg.norm(fallback[0]) == pytest.approx(1)
    assert embedder.embed([]).shape == (0, 1024)
    # Full tokens must not confuse C1 with C10 or P1 with P10.
    assert not np.array_equal(embedder.embed(['취침_CL0-P0-C10']), embedder.embed(['취침_CL0-P0-C1']))


class QueryOut(BaseModel):
    persona_query: dict[str, list[str]]
    context_queries: dict[str, dict[str, str]]
    anchor_context_ids: list[str]


class ItemsOut(BaseModel):
    items: list[dict]


def response(backend, name, schema):
    result = backend.run(LLMTask(task=name, sid='fixture', instructions='fixture',
                                attachments=[], output_schema=schema))
    assert result.ok, result.error
    return result.data.model_dump()


def test_fake_queries_anchor_all_contexts_and_tag_quotes_are_verbatim(ready):
    contexts = SegmentStore.open(ready.sid, ready.version).contexts()
    docs = dict(list(load_input(ready.sid, ready.version).docs.items())[:3])
    docs['comment-only'] = dict(title='', body='', comments=[{'text': '예약 운전이 편해요. 다음에도 쓸래요.'}])
    backend = fake_evidence_backend(contexts, docs)
    assert isinstance(backend, FakeBackend)
    query = response(backend, 'evidence.queries', QueryOut)
    ids = {c['context_id'] for c in contexts}
    assert set(query['anchor_context_ids']) == set(query['context_queries']) == ids
    assert len(query['persona_query']['desire_check']) == 2
    assert len(query['persona_query']['artifact']) == 1
    assert not re.search(r'페르소나|클러스터|컨텍스트|세그먼트|인사이트|소비자는|사용자는|고객은', json.dumps(query, ensure_ascii=False))
    for queries in query['context_queries'].values():
        assert set(queries) == {'Sense', 'Feel', 'Think', 'Act', 'Relate', 'Outcome', 'Counter', 'Residual'}
        assert all(queries.values())
    items = response(backend, 'evidence.tag', ItemsOut)['items']
    assert {item['doc_id'] for item in items} == set(docs)
    for item in items:
        assert set(item) == {'doc_id', 'relevant', 'reason_code', 'polarity', 'pain_point', 'unmet_need', 'situation', 'context_dims', 'artifacts', 'known_match', 'quotes'}
        assert item['quotes']
        for quote in item['quotes']:
            doc = docs[item['doc_id']]
            text = doc['comments'][quote['idx']]['text'] if quote['field'] == 'comment' else doc[quote['field']]
            assert quote['text'] and quote['text'] in text
        assert item['pain_point']['quote'] in [q['text'] for q in item['quotes']]
    novelty = response(backend, 'evidence.novelty', ItemsOut)['items']
    assert {item['doc_id'] for item in novelty} == set(docs)
    assert all(item['novelty'] in {'none', 'low', 'medium', 'high', 'very_high'} and item['reason'] for item in novelty)


@pytest.mark.parametrize('name,schema', [('evidence.queries', QueryOut), ('evidence.tag', ItemsOut), ('evidence.novelty', ItemsOut)])
def test_default_fake_backend_has_evidence_examples(name, schema):
    assert response(FakeBackend(), name, schema)


def test_tag_helper_only_supplies_missing_dims():
    docs = {
        'existing': {'body': '예약을 설정했어요.', 'context_dims': {'environment': '침실'}},
        'supporting': {'body': '예약을 설정했어요.', 'evidence_level_pred': 'supporting'},
        'core': {'body': '예약을 설정했어요.', 'evidence_level_pred': 'core'},
    }
    tags = {row['doc_id']: row for row in response(fake_evidence_backend([], docs), 'evidence.tag', ItemsOut)['items']}
    assert tags['existing']['situation'] is None
    assert tags['existing']['context_dims'] is None
    assert tags['supporting']['situation'] and tags['supporting']['context_dims'] is None
    assert tags['core']['situation'] and tags['core']['context_dims']
