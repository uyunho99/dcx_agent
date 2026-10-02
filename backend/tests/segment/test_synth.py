"""Contracts for the shared, offline stage-six fixture."""
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
from pydantic import BaseModel, ConfigDict

from app.context import store
from app.known.filter import read_export, read_jsonl
from app.model.infer import documents, prepared_root
from app.vectors.store import VectorStore
from app.llm.base import LLMTask
from app.llm.fake import FakeBackend
from tests.fixtures.segment_synth import make_segment_session, fake_dims_backend

PERSONAS = (2, 3, 2, 3, 2)
CONTEXTS = (2, 3, 2, 2, 3, 2, 2, 3, 2, 2, 2, 3)[:sum(PERSONAS)]


@pytest.fixture
def synth(data_dir):
    return make_segment_session(data_dir, clusters=5, personas=PERSONAS,
                                contexts=CONTEXTS, docs_per_context=40, seed=0)


def artifacts(synth):
    data = store.load_session(synth.sid)
    root = prepared_root(synth.sid, data)
    return root, read_export(synth.sid, data)


def test_synth_shapes(synth):
    root, rows = artifacts(synth)
    assert synth.expected['k'] == 5
    assert synth.version == 'v1'
    assert len(rows) == sum(CONTEXTS) * 40
    assert len({r['doc_id'] for r in rows}) == len(rows)
    required = {'title', 'body', 'comments', 'source', 'author_hash', 'date',
                'evidence_level_pred', 'tagProbs'}
    assert all(required <= row.keys() for row in rows)
    assert {r['evidence_level_pred'] for r in rows} == {'core', 'supporting'}
    assert {r['source'] for r in rows} == {'agreed'}
    assert all('channel' not in r for r in rows)
    prepared = documents(synth.sid, store.load_session(synth.sid))
    assert {r['source'] for r in prepared.values()} == {
        'naver_cafe', 'naver_blog', 'youtube', 'ppomppu', 'clien'}
    assert all(r['author_hash'] and r['date'] and r['comments'][0]['author_hash']
               for r in prepared.values())


def test_synth_vectors_separable(synth):
    root, rows = artifacts(synth)
    ids, vectors = VectorStore(root).get([r['doc_id'] for r in rows])
    assert vectors.shape == (len(rows), 1024)
    norms = np.linalg.norm(vectors, axis=1)
    assert {ids[i] for i in np.flatnonzero(norms == 0)} == set(synth.expected['zero_vector_ids'])
    assert len(synth.expected['zero_vector_ids']) == 2
    np.testing.assert_allclose(norms[norms > 0], 1, atol=.001)
    groups = np.array([synth.expected['assignments'][i]['cluster'] for i in ids])
    means = []
    for group in sorted(set(groups)):
        matrix = vectors[(groups == group) & (norms > 0)]
        cos = matrix @ matrix.T
        assert (cos.sum() - np.trace(cos)) / (len(matrix) * (len(matrix) - 1)) >= .7
        means.append(matrix.mean(axis=0))
    for i, left in enumerate(means):
        for right in means[i + 1:]:
            assert left @ right / (np.linalg.norm(left) * np.linalg.norm(right)) <= .2
    shard = next((root / 'vectors').glob('*.f16'))
    assert shard.stat().st_size == len(rows) * 1024 * 2


def test_synth_vocab_structure(synth):
    root, _ = artifacts(synth)
    vocab = synth.expected
    for key, size, count in [('persona_nouns', 10, sum(PERSONAS)),
                              ('context_tokens', 8, sum(CONTEXTS))]:
        sets = [set(words) for words in vocab[key].values()]
        assert len(sets) == count
        assert all(len(words) == size for words in sets)
        assert len(set.union(*sets)) == size * count
    tokens = {r['doc_id']: r['tokens'] for p in (root / 'tokens').glob('*.jsonl') for r in read_jsonl(p)}
    assert [i for i, words in tokens.items() if not words] == vocab['no_token_ids']
    assert len(vocab['no_token_ids']) == 1
    assert not set(vocab['no_token_ids']) & set(vocab['zero_vector_ids'])
    for doc_id, assignment in vocab['assignments'].items():
        if doc_id in vocab['no_token_ids']:
            continue
        assert set(vocab['persona_nouns'][assignment['persona']]) <= set(tokens[doc_id])
        assert set(vocab['context_tokens'][assignment['context']]) <= set(tokens[doc_id])
        assert all('/' not in token for token in tokens[doc_id])


def test_synth_session_readable_by_pipeline_inputs(synth, data_dir):
    data = store.load_session(synth.sid)
    root, rows = artifacts(synth)
    ref = data['prep']['derivedRef']
    assert root == data_dir / 'derived' / synth.sid / ref['collectionId'] / ref['prepKey']
    assert all((root / name).is_dir() for name in ('docs', 'tokens', 'vectors'))
    assert (data_dir / data['training']['exportRef']).is_file()
    assert store.assert_writable(synth.sid, synth.version)['version'] == 'v1'
    assert store.read_json(data_dir / data['training']['stage5Ref'])
    assert len(documents(synth.sid, data)) == len(rows)
    from app.routers.sessions import _completion
    completion = _completion(synth.sid, data)
    assert all(completion[key] for key in ('crawlDone', 'prepDone', 'labelingDone', 'exportDone'))


def test_synth_deterministic_and_restores_settings(data_dir):
    from app.config import settings
    before = (settings.local_data_dir, settings.embed_backend, settings.llm_backend)
    a = make_segment_session(data_dir / 'a', docs_per_context=2)
    b = make_segment_session(data_dir / 'b', docs_per_context=2)
    assert a == b
    for directory in ('derived', 'classified'):
        left = {p.relative_to(data_dir / 'a'): p.read_bytes() for p in (data_dir / 'a' / directory).rglob('*')
                if p.suffix in ('.f16', '.jsonl')}
        right = {p.relative_to(data_dir / 'b'): p.read_bytes() for p in (data_dir / 'b' / directory).rglob('*')
                 if p.suffix in ('.f16', '.jsonl')}
        assert left == right
    assert before == (settings.local_data_dir, settings.embed_backend, settings.llm_backend)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Name(StrictModel):
    name: str


class Persona(Name):
    desire: str
    goals: list[str]


class Context(Name):
    action: str


class Dim(StrictModel):
    doc_id: str
    environment: str | None
    internal_state: str | None
    task_goal: str | None
    activity_response: str | None
    resource_constraint: str | None


class Dims(StrictModel):
    items: list[Dim]


@pytest.mark.parametrize('name,schema', [('cluster_name', Name), ('persona_draft', Persona),
                                         ('context_draft', Context), ('dims', Dims)])
def test_fake_llm_contract(name, schema):
    task = LLMTask(task=f'segment.{name}', sid='synth', instructions='합성 응답',
                   attachments=[], output_schema=schema)
    result = FakeBackend().run(task)
    assert result.ok, result.error
    if name == 'dims':
        ids = ['batch-a', 'batch-b']
        result = fake_dims_backend(ids).run(task)
        assert result.ok, result.error
        assert [item.doc_id for item in result.data.items] == ids


def test_qa_script(tmp_path):
    script = Path(__file__).resolve().parents[1] / 'scripts/make_segment_qa.py'
    result = subprocess.run([sys.executable, str(script), str(tmp_path)], capture_output=True,
                            text=True, env={**os.environ, 'EMBED_BACKEND': 'fake', 'LLM_BACKEND': 'fake'})
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary['documents'] == 1200
    session = store.read_json(tmp_path / 'sessions' / summary['sid'] / 'versions/v1/session.json')
    rows = read_jsonl(tmp_path / session['training']['exportRef'])
    assert len(rows) == 1200
    assert all('LG' in row['title'] and '에어컨' in row['body'] for row in rows)
