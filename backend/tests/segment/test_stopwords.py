"""D-246/D-249: filter output keywords without changing LDA training."""
import hashlib
import json

import pytest

from app.context import store as sessions
from app.context.versions import version_dir
from app.segment import ctfidf, l2, l3, params, pipeline, stopwords
from app.segment.store import SegmentStore
from tests.segment.test_l3 import persona
from tests.segment.test_pipeline import Context, setup  # noqa: F401 (shared offline fixture)


def test_is_stopword_rules():
    for word in ('사용', '생각', '가', '2024', '에어컨', 'LG에어컨', 'LG 에어 컨', ''):
        assert stopwords.is_stopword(word, '에어 컨'), word
    assert not stopwords.is_stopword('냉방', '에어컨')
    for bk in (None, '', '   '):
        assert not stopwords.is_stopword('냉방', bk)
    assert stopwords.filter_words(iter(['냉방', '사용', '전기료', '냉방', 'LG에어컨']), '에어컨') == ['냉방', '전기료', '냉방']


def test_domain_words_not_stopwords():
    for word in ('가격', '구매', '구입', '추천', '사진', '냉방', '소음', '전기료', '필터', '설치'):
        assert stopwords.is_stopword(word, '') is False, word


def test_list_size_and_editable(monkeypatch):
    assert isinstance(stopwords.STOPWORDS, frozenset)
    assert 80 <= len(stopwords.STOPWORDS) <= 150
    assert [key for key in vars(stopwords) if key.isupper()] == ['STOPWORDS']
    expected = hashlib.sha256('\n'.join(sorted(stopwords.STOPWORDS)).encode()).hexdigest()[:12]
    assert stopwords.stopwords_signature() == {'count': len(stopwords.STOPWORDS), 'hash': expected}
    monkeypatch.setattr(stopwords, 'STOPWORDS', stopwords.STOPWORDS | {'냉방'})
    assert stopwords.is_stopword('냉방', None)
    assert stopwords.stopwords_signature()['hash'] != expected


def test_l2_network_excludes_stopwords(monkeypatch):
    monkeypatch.setattr(params, 'L2_VOCAB', 6)
    useful = {'냉방', '전기료', '소음', '필터', '청소', '먼지'}
    nouns = {str(i): ['사용', '생각', '가', '2024', '에어컨', 'LG에어컨']
             + (['냉방', '전기료', '소음'] if i < 20 else ['필터', '청소', '먼지'])
             for i in range(40)}
    result = l2.personas(list(nouns), nouns, '에어컨')
    assert {node['id'] for node in result.network['nodes']} == useful
    assert all(len(words) <= 16 for words in result.centrality)
    assert {word for words in result.centrality for word, _ in words} == useful
    assert {word for words in result.communities for word in words} == useful
    assert not l2.personas(['noise'], {'noise': ['사용', '생각']}, '').network['nodes']


def test_ctfidf_keywords_exclude_stopwords():
    groups = {'a': [['사용'] * 100 + ['LG에어컨'] * 80 + ['2024'] * 60 + ['가'] * 40 + ['냉방'] * 3 + ['전기료'] * 2 + ['소음']]}
    assert ctfidf.ctfidf(groups, 3, bk='에어 컨')['a'] == ['냉방', '전기료', '소음']
    assert ctfidf.ctfidf({'a': [['사용', '생각']]}, 10) == {'a': []}
    assert ctfidf.ctfidf(groups, 0, bk='에어컨') == {'a': []}


@pytest.fixture(scope='module')
def lda_comparison():
    # Two fixed Personas, with stopwords surviving Dictionary.filter_extremes.
    results = []
    for sizes in ((20, 20), (15, 15, 15)):
        ids, tokens, vectors = persona(sizes)
        for doc in ids[:sizes[0]]:
            tokens[doc] += ['사용'] * 20 + ['LG에어컨'] * 20
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(stopwords, 'is_stopword', lambda word, bk: False)
            before = l3.contexts(ids, tokens, vectors, bk='에어컨')
        after = l3.contexts(ids, tokens, vectors, bk='에어컨')
        results.append((before, after))
    return results


def test_context_keywords_exclude_stopwords(lda_comparison):
    for before, after in lda_comparison:
        assert any('사용' in words and 'LG에어컨' in words for words in before.topic_words.values())
        assert all(len(words) == params.CTFIDF_TOP for words in after.topic_words.values())
        assert all(not stopwords.is_stopword(word, '에어컨') for words in after.topic_words.values() for word in words)


def test_lda_topic_count_unchanged(lda_comparison):
    for before, after in lda_comparison:
        assert before.scan == after.scan
        assert before.topic_ids == after.topic_ids
        assert before.assign == after.assign
        assert before.theta_all == after.theta_all
        assert len(before.topic_ids) == len(after.topic_ids)


def test_stage6_params_record_stopwords(setup, monkeypatch):
    fixture, _ = setup(docs_per_context=4)
    path = version_dir(fixture.sid, 'v1') / 'session.json'
    session = sessions.read_json(path)
    session['projectContext'] = {'bk': '에어 컨'}
    sessions.write_json(path, session)
    original = pipeline.inputs.load_input
    def loaded(*args, **kwargs):
        source = original(*args, **kwargs)
        for doc in source.ids:
            source.nouns[doc] += ['사용', '생각', 'LG에어컨'] * 20
        return source
    monkeypatch.setattr(pipeline.inputs, 'load_input', loaded)
    original_contexts = pipeline.l3.contexts
    def contexts(*args, **kwargs):
        assert kwargs['bk'] == '에어 컨'
        return original_contexts(*args, **kwargs)
    monkeypatch.setattr(pipeline.l3, 'contexts', contexts)
    pipeline.run(Context(fixture.sid))
    result = sessions.read_json(version_dir(fixture.sid, 'v1') / 'segment/stage_6.json')
    assert result['params']['stopwords'] == stopwords.stopwords_signature()
    store = SegmentStore.open(fixture.sid, 'v1')
    for row in store.clusters() + store.contexts():
        assert all(not stopwords.is_stopword(word, '에어컨') for word in row['keywords'])

    # Completed resumes must retain old output and its original fingerprint.
    def snapshot():
        return json.dumps({layer: getattr(store, layer)()
                           for layer in ('clusters', 'personas', 'contexts')}, default=pipeline._json)
    before = snapshot()
    monkeypatch.setattr(stopwords, 'STOPWORDS', stopwords.STOPWORDS | {'새불용어'})
    resumed = pipeline.run(Context(fixture.sid))
    assert resumed['params']['stopwords'] == result['params']['stopwords']
    assert resumed['params']['stopwords'] != stopwords.stopwords_signature()
    assert before == snapshot()

    # A pre-T1 checkpoint must not claim the current filter produced its data.
    checkpoint_path = version_dir(fixture.sid, 'v1') / 'segment/checkpoint.json'
    checkpoint = sessions.read_json(checkpoint_path)
    checkpoint.pop('stopwords')
    sessions.write_json(checkpoint_path, checkpoint)
    assert 'stopwords' not in pipeline.run(Context(fixture.sid))['params']
    assert before == snapshot()
