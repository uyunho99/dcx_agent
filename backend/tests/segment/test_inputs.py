import json
from collections import Counter
from types import SimpleNamespace

import numpy as np
import pytest

from app.context import store
from app.context.versions import version_dir
from app.model.infer import documents, prepared_root
from app.prep import tokens as prep_tokens
from app.segment.inputs import load_input
from tests.fixtures.segment_synth import make_segment_session


@pytest.fixture
def session(data_dir):
    return make_segment_session(data_dir, clusters=1, personas=(2,), contexts=(2, 2), docs_per_context=4)


def snapshot(session):
    return store.read_json(version_dir(session.sid, session.version) / 'session.json')


def write_rows(path, rows):
    store.atomic_write(path, ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))


def test_input_exclusions_float16_normalization_and_truncation(session):
    data = snapshot(session)
    root = prepared_root(session.sid, data)
    docs = documents(session.sid, data)
    docs['d000003']['body'] = '가' * 2001
    docs['d000004']['comments'] = [{'text': '나' * 2001}]
    for path in (root / 'docs').glob('*.jsonl'):
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        write_rows(path, [docs[r['doc_id']] for r in rows])
    result = load_input(session.sid, session.version)
    assert len(result.ids) == session.expected['documents'] - 3
    assert not set(result.ids) & set(session.expected['zero_vector_ids'] + session.expected['no_token_ids'])
    assert set(result.ids) == set(result.tokens) == set(result.nouns) == set(result.docs)
    assert result.vectors.dtype == np.float16
    np.testing.assert_allclose(np.linalg.norm(result.vectors.astype(np.float32), axis=1), 1, atol=.001)
    assert result.report == dict(relevant=16, zero_vector=2, no_tokens=1, truncated=2,
                                by_channel=dict(Counter(docs[i]['source'] for i in result.ids)))
    for doc_id in result.ids:
        assert result.nouns[doc_id] == result.tokens[doc_id]
        assert all(isinstance(t, str) for t in result.tokens[doc_id])


def test_channel_from_derived_not_export(session):
    data = snapshot(session)
    prepared = documents(session.sid, data)
    path = version_dir(session.sid, session.version).parents[3] / data['training']['exportRef']
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    for row in rows:
        row['source'] = 'agreed'
        for key in ('author_hash', 'comments', 'date'):
            row.pop(key, None)
    write_rows(path, rows)
    result = load_input(session.sid, session.version)
    assert 'agreed' not in result.report['by_channel']
    assert sum(result.report['by_channel'].values()) == len(result.ids)
    for doc_id, doc in result.docs.items():
        assert doc['judge_source'] == 'agreed'
        for key in ('source', 'author_hash', 'comments', 'date'):
            assert doc[key] == prepared[doc_id][key]
        assert doc['tagProbs']
        assert doc['evidence_level_pred'] in {'core', 'supporting'}


def test_nouns_cached_next_to_derived(session, monkeypatch):
    data = snapshot(session)
    root = prepared_root(session.sid, data)
    manifest = store.read_json(root / 'manifest.json')
    manifest['config']['tokenPos'] = ['NNG', 'NNP', 'VV']
    store.write_json(root / 'manifest.json', manifest)
    calls = []
    def kiwi():
        calls.append(1)
        return SimpleNamespace(tokenize=lambda text: [SimpleNamespace(form='냉방', tag='NNG'),
                                                       SimpleNamespace(form='하다', tag='VV')])
    monkeypatch.setattr(prep_tokens, '_kiwi', kiwi)
    writes = []
    original = store.atomic_write
    def atomic(path, text):
        writes.append(path)
        original(path, text)
    monkeypatch.setattr(store, 'atomic_write', atomic)
    result = load_input(session.sid, session.version)
    assert calls
    assert all(n == ['냉방'] for n in result.nouns.values())
    assert list((root / 'nouns').glob('part-*.jsonl'))
    assert any(p.parent == root / 'nouns' and p.name.startswith('part-') for p in writes)
    calls.clear()
    assert load_input(session.sid, session.version).nouns == result.nouns
    assert not calls
    store.write_json(version_dir(session.sid, 'v2') / 'session.json', data)
    assert load_input(session.sid, 'v2').nouns == result.nouns
    assert not calls
    # A partial generation is not a cache, regardless of plausible row contents.
    (root / 'nouns/manifest.json').unlink()
    write_rows(root / 'nouns/part-99999.jsonl', [{'doc_id': result.ids[0], 'nouns': ['partial']}])
    assert load_input(session.sid, 'v2').nouns == result.nouns
    assert calls
    assert not (root / 'nouns/part-99999.jsonl').exists()


def test_missing_tokens_requires_reprep(session):
    root = prepared_root(session.sid, snapshot(session))
    for path in (root / 'tokens').glob('*.jsonl'):
        path.unlink()
    with pytest.raises(store.StoreError, match='토큰'):
        load_input(session.sid, session.version)


def test_noun_only_tokens_need_no_kiwi(session, monkeypatch):
    def unexpected():
        pytest.fail('Noun-only preparation should not invoke Kiwi')
    monkeypatch.setattr(prep_tokens, '_kiwi', unexpected)
    first = load_input(session.sid, session.version)
    second = load_input(session.sid, session.version)
    assert first.nouns == first.tokens == second.nouns


def test_damaged_completed_cache_is_rebuilt(session):
    first = load_input(session.sid, session.version)
    root = prepared_root(session.sid, snapshot(session))
    part = next((root / 'nouns').glob('part-*.jsonl'))
    store.atomic_write(part, '{broken json')
    assert load_input(session.sid, session.version).nouns == first.nouns
    part.unlink()
    assert load_input(session.sid, session.version).nouns == first.nouns


def test_empty_relevant_input(session, data_dir):
    data = snapshot(session)
    store.atomic_write(data_dir / data['training']['exportRef'], '')
    result = load_input(session.sid, session.version)
    assert result.ids == []
    assert result.vectors.shape == (0, 1024)
    assert result.vectors.dtype == np.float16
    assert result.report == dict(relevant=0, zero_vector=0, no_tokens=0, truncated=0, by_channel={})


def test_failed_cache_publication_is_rebuilt(session, monkeypatch):
    root = prepared_root(session.sid, snapshot(session))
    original = store.atomic_write
    def interrupted(path, text):
        if path == root / 'nouns/manifest.json':
            raise OSError('simulated interruption')
        original(path, text)
    with monkeypatch.context() as patch:
        patch.setattr(store, 'atomic_write', interrupted)
        with pytest.raises(OSError, match='simulated interruption'):
            load_input(session.sid, session.version)
    assert list((root / 'nouns').glob('part-*.jsonl'))
    assert not (root / 'nouns/manifest.json').exists()
    assert len(load_input(session.sid, session.version).ids) == 13
    assert store.read_json(root / 'nouns/manifest.json')['status'] == 'done'
