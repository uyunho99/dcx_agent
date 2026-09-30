import json
from contextlib import closing
from app.crawl.queue import CrawlQueue

import numpy as np
import pytest

from app.config import settings
from app.context import store
from app.prep import pipeline
from app.prep.config import PrepConfig, prep_key
from app.vectors.store import VectorStore


class Context:
    def __init__(self, config=None, stop_after=None):
        self.args = {'config': config or {}}
        self.stop_after = stop_after
        self.completed = 0

    def heartbeat(self, progress, detail):
        self.completed = detail.get('done_shards', 0)

    def should_stop(self):
        return self.stop_after is not None and self.completed >= self.stop_after

    def should_pause(self):
        return False


class Embedder:
    name, model, dim = 'fake', 'voyage-4', 1024

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def embed(self, texts):
        self.calls.append(texts)
        if self.fail:
            raise RuntimeError('offline failure')
        return np.ones((len(texts), self.dim), dtype=np.float32)


def doc(i='d1', **kwargs):
    return dict(doc_id=i, source='naver_cafe', title='제목',
                body='육아맘 사용 경험이 충분히 길어요?!', comments=[],
                url='https://example.test/' + i, fetch_level='full', src_meta={}, **kwargs)


def rows(root, kind):
    return [json.loads(line) for path in sorted((root / kind).glob('*.jsonl'))
            for line in path.read_text().splitlines()]


@pytest.fixture
def setup(data_dir, monkeypatch):
    embedder = Embedder()
    monkeypatch.setattr(settings, 'embed_backend', 'fake')
    monkeypatch.setattr(pipeline, 'get_embedder', lambda: embedder)
    def prepare(docs, config=None):
        root = data_dir / 'crawl/s/collections/c1'
        store.write_json(root / 'manifest.json', {'parent': None})
        with closing(CrawlQueue(root / 'queue.sqlite')) as queue:
            queue.finish_run(queue.register_run('detail'), 'done')
        store.atomic_write(root / 'docs/shard-0001.jsonl', ''.join(json.dumps(d) + '\n' for d in docs))
        store.update_session('s', {'schemaVersion': 2, 'collectionId': 'c1',
                                   'prep': {'config': config or {}}})
        return embedder
    return prepare


def test_filters_use_body(setup):
    documents = [doc(), {**doc('ad'), 'body': 'x' * 4100 + '광고'},
                 {**doc('short'), 'title': '충분히 긴 제목', 'body': '짧음'},
                 {**doc('excluded'), 'source': 'youtube'},
                 {**doc('comment'), 'comments': [{'text': '광고'}]}]
    setup(documents)
    root = pipeline.run_prep(Context({'adFilter': ['광고'], 'excludeSources': ['youtube']}), 's', 'v1')
    assert [d['doc_id'] for d in rows(root, 'docs')] == ['d1']
    assert json.loads((root / 'stage_3.json').read_text())['removed'] == {
        'ad': 2, 'excluded_source': 1, 'duplicate': 0, 'too_short': 1}


def test_no_target_word_filter(setup):
    setup([doc()])
    assert len(rows(pipeline.run_prep(Context(), 's', 'v1'), 'docs')) == 1


def test_boilerplate_removed_counted(setup):
    phrase = '카페 회원이 되시면 전체 내용을 볼 수 있습니다.'
    setup([{**doc(), 'body': phrase + doc()['body'], 'comments': [{'text': phrase + '댓글!'}]}])
    root = pipeline.run_prep(Context({'boilerplate': {'naver_cafe': [phrase]}}), 's', 'v1')
    result = rows(root, 'docs')[0]
    assert phrase not in result['body'] and result['comments'][0]['text'] == '댓글!'
    assert json.loads((root / 'stage_3.json').read_text())['boilerplate_replaced']['naver_cafe'] == 2


def test_two_paths(setup, monkeypatch):
    embedder = setup([{**doc(), 'body': '<b>충분히 긴 본문인가요?!</b>'}])
    inputs = []
    monkeypatch.setattr(pipeline, 'tokenize', lambda text, pos: inputs.append(text) or ['본문'])
    root = pipeline.run_prep(Context(), 's', 'v1')
    assert '?' not in inputs[0] and '!' not in inputs[0]
    assert '?!' in embedder.calls[0][0] and '?!' in rows(root, 'docs')[0]['body']
    assert '<b>' not in embedder.calls[0][0]


def test_tokens_written(setup):
    setup([doc()])
    root = pipeline.run_prep(Context(), 's', 'v1')
    result = rows(root, 'tokens')[0]
    assert (root / 'tokens/part-00001.jsonl').exists()
    assert result['doc_id'] == 'd1' and '경험' in result['tokens']


def test_prep_key_reuse(setup):
    embedder = setup([doc()])
    first = pipeline.run_prep(Context(), 's', 'v1')
    assert pipeline.run_prep(Context(), 's', 'v1') == first
    assert len(embedder.calls) == 1
    assert prep_key('c1', PrepConfig(adFilter=['b', 'a']), embedder) == prep_key(
        'c1', PrepConfig(adFilter=['a', 'b']), embedder)
    assert prep_key('c2', PrepConfig(), embedder) != prep_key('c1', PrepConfig(), embedder)


def test_embed_failure_zero_vector(setup):
    embedder = setup([doc()])
    embedder.fail = True
    root = pipeline.run_prep(Context(), 's', 'v1')
    assert len(embedder.calls) == 3
    assert not VectorStore(root).get(['d1'])[1].any()
    assert next(VectorStore(root).iter_shards())[2].tolist() == [True]
    assert json.loads((root / 'stage_3.json').read_text())['embed_failed_zero_vector'] == 1


def test_resume_skips_done_shards(setup, monkeypatch):
    monkeypatch.setattr(pipeline, 'SHARD_ROWS', 2)
    embedder = setup([doc(str(i)) for i in range(6)])
    root = pipeline.run_prep(Context(stop_after=2), 's', 'v1')
    assert len(embedder.calls) == 2
    assert json.loads((root / 'manifest.json').read_text())['status'] == 'interrupted'
    pipeline.run_prep(Context(), 's', 'v1')
    assert len(embedder.calls) == 3
    assert len(rows(root, 'docs')) == VectorStore(root).count() == 6


def test_stage3_report_contract(setup):
    setup([doc()])
    root = pipeline.run_prep(Context(), 's', 'v1')
    report = json.loads((root / 'stage_3.json').read_text())
    assert set(report) == {'original', 'after', 'removed', 'boilerplate_replaced',
                           'tokens_written', 'embedded', 'embed_failed_zero_vector',
                           'prepKey', 'embedder', 'analyzer', 'at'}
    assert report['original'] == report['after'] == report['tokens_written'] == report['embedded'] == 1
    assert report['embedder'] == 'voyage-4' and report['analyzer'].startswith('kiwi-0.24')


def test_done_cache_does_not_read_collection_again(setup, monkeypatch):
    setup([doc()])
    root = pipeline.run_prep(Context(), 's', 'v1')
    def forbidden(*args, **kwargs):
        raise AssertionError('completed cache must return without collection IO')
    monkeypatch.setattr(pipeline, '_crawl_docs', forbidden)
    assert pipeline.run_prep(Context(), 's', 'v1') == root


def test_crash_after_vector_publication_does_not_reembed(setup, monkeypatch):
    embedder = setup([doc()])
    original = VectorStore.write_shard
    def crash(self, *args):
        original(self, *args)
        raise RuntimeError('simulated process failure after vector publication')
    monkeypatch.setattr(VectorStore, 'write_shard', crash)
    with pytest.raises(RuntimeError):
        pipeline.run_prep(Context(), 's', 'v1')
    monkeypatch.setattr(VectorStore, 'write_shard', original)
    root = pipeline.run_prep(Context(), 's', 'v1')
    assert len(embedder.calls) == VectorStore(root).count() == 1
    assert json.loads((root / 'manifest.json').read_text())['status'] == 'done'


def test_batch_limit_truncation_and_zero_result_retry(setup):
    embedder = setup([{**doc(str(i)), 'body': '본문' * 1200} for i in range(129)])
    calls = []
    def embed(texts):
        calls.append(texts)
        return np.zeros((len(texts), 1024), dtype=np.float32)
    embedder.embed = embed
    root = pipeline.run_prep(Context(), 's', 'v1')
    assert [len(c) for c in calls] == [128, 128, 128, 1, 1, 1]
    assert all(len(text) == 2000 for call in calls for text in call)
    assert json.loads((root / 'stage_3.json').read_text())['embed_failed_zero_vector'] == 129


def test_version_snapshot_and_compat_output(setup, data_dir):
    setup([doc()])
    current = store.load_session('s')
    store.write_json(data_dir / 'sessions/s/versions/v2/session.json',
                     {**current, 'collectionId': 'c2', 'version': 'v2'})
    # Leave active pointer on v1: an explicit v2 worker must not read v1 documents.
    source = data_dir / 'crawl/s/collections/c2'
    store.write_json(source / 'manifest.json', {'parent': None})
    with closing(CrawlQueue(source / 'queue.sqlite')) as queue:
        queue.finish_run(queue.register_run('detail'), 'done')
    store.atomic_write(source / 'docs/shard-0001.jsonl', json.dumps(doc('v2doc')) + '\n')
    root = pipeline.run_prep(Context(), 's', 'v2')
    assert rows(root, 'docs')[0]['doc_id'] == 'v2doc'
    assert store.load_session('s')['prep'].get('status') is None
    saved = store.read_json(data_dir / 'sessions/s/versions/v2/session.json')
    assert saved['prep']['derivedRef'] == {'collectionId': 'c2', 'prepKey': root.name}
    compat = next((data_dir / 'preprocessed/s').glob('*.jsonl'))
    assert [json.loads(line) for line in compat.read_text().splitlines()] == rows(root, 'docs')


def test_pause_and_empty_input(setup):
    setup([])
    class Paused(Context):
        def __init__(self):
            super().__init__()
            self.checks = 0
        def should_pause(self):
            self.checks += 1
            return self.checks == 1
    context = Paused()
    root = pipeline.run_prep(context, 's', 'v1')
    assert context.checks >= 2
    assert json.loads((root / 'stage_3.json').read_text())['after'] == 0


def test_clean_defaults_and_key_changes():
    from app.prep.clean import clean_html, token_text
    from app.prep.tokens import tokenize
    assert clean_html('<p>본문 &amp; 글</p><script>광고</script><p>다음!</p>') == '본문 & 글\n다음!'
    assert token_text('경험?! ★😊 + 만족') == '경험 만족'
    assert tokenize('경험이 좋았다', ['NNG']) == ['경험']
    cfg = PrepConfig()
    assert cfg.minBodyChars == 10 and cfg.embedModel == 'voyage-4' and cfg.embedDim == 1024
    assert cfg.tokenPos == ['NNG', 'NNP', 'VV', 'VA', 'XR']
    cfg.boilerplate['naver_cafe'].append('추가')
    assert '추가' not in PrepConfig().boilerplate['naver_cafe']
    assert prep_key('c1', cfg, Embedder()) != prep_key('c1', PrepConfig(), Embedder())


@pytest.mark.parametrize('failure_at', ['factory', 'embed'])
def test_unconnected_stops_without_vectors_and_can_resume(setup, monkeypatch, data_dir, failure_at):
    from app.vectors.embedder import EmbedderUnconnected, FakeEmbedder
    setup([doc()])
    monkeypatch.setattr(settings, 'embed_backend', 'voyage')
    working = FakeEmbedder()
    working.name = 'voyage'
    cfg = PrepConfig(embedder='voyage')
    root = data_dir / 'derived/s/c1' / prep_key('c1', cfg, working)

    def unconnected(*args):
        raise EmbedderUnconnected('not configured')

    if failure_at == 'factory':
        monkeypatch.setattr(pipeline, 'get_embedder', unconnected)
    else:
        unavailable = Embedder()
        unavailable.name = 'voyage'
        unavailable.embed = unconnected
        monkeypatch.setattr(pipeline, 'get_embedder', lambda: unavailable)
    with pytest.raises(EmbedderUnconnected):
        pipeline.run_prep(Context({'embedder': 'voyage'}), 's', 'v1')
    manifest = store.read_json(root / 'manifest.json')
    assert manifest is None or manifest['status'] != 'done'
    assert VectorStore(root).count() == 0
    assert not list((root / 'vectors').glob('*.f16'))

    monkeypatch.setattr(pipeline, 'get_embedder', lambda: working)
    assert pipeline.run_prep(Context({'embedder': 'voyage'}), 's', 'v1') == root
    assert store.read_json(root / 'manifest.json')['status'] == 'done'
    assert VectorStore(root).get(['d1'])[1].any()
    assert store.read_json(root / 'stage_3.json')['embed_failed_zero_vector'] == 0


@pytest.mark.parametrize('recover', [True, False])
def test_resume_retries_failed_rows_in_completed_shard(setup, monkeypatch, recover):
    monkeypatch.setattr(pipeline, 'BATCH_ROWS', 1)
    embedder = setup([{**doc(i), 'title': i} for i in ['good', 'bad']])
    original = embedder.embed

    def fail_one(texts):
        embedder.fail = 'bad' in texts[0]
        return original(texts)

    embedder.embed = fail_one
    root = pipeline.run_prep(Context(stop_after=1), 's', 'v1')
    assert store.read_json(root / 'manifest.json')['status'] == 'interrupted'
    assert len(embedder.calls) == 4
    assert sum(int(flags.sum()) for _, _, flags in VectorStore(root).iter_shards()) == 1
    before = VectorStore(root).get(['good'])[1].copy()
    embedder.embed = original
    embedder.fail = not recover
    embedder.calls.clear()
    assert pipeline.run_prep(Context(), 's', 'v1') == root
    assert len(embedder.calls) == (1 if recover else 3)
    assert all('bad' in call[0] for call in embedder.calls)
    assert VectorStore(root).count() == 2
    np.testing.assert_array_equal(VectorStore(root).get(['good'])[1], before)
    assert bool(VectorStore(root).get(['bad'])[1].any()) == recover
    report = store.read_json(root / 'stage_3.json')
    assert report['embed_failed_zero_vector'] == (0 if recover else 1)
    assert report['embedded'] == (2 if recover else 1)
    assert sum(int(flags.sum()) for _, _, flags in VectorStore(root).iter_shards()) == (0 if recover else 1)
    calls = len(embedder.calls)
    assert pipeline.run_prep(Context(), 's', 'v1') == root
    assert len(embedder.calls) == calls


def test_retry_interrupted_before_failure_flags_are_published(setup, monkeypatch):
    embedder = setup([doc()])
    embedder.fail = True
    root = pipeline.run_prep(Context(stop_after=1), 's', 'v1')
    embedder.fail = False
    original = pipeline._jsonl

    def interrupt(path, records):
        if path.name == 'ids.jsonl':
            raise RuntimeError('interrupted before index publication')
        return original(path, records)

    monkeypatch.setattr(pipeline, '_jsonl', interrupt)
    with pytest.raises(RuntimeError, match='index publication'):
        pipeline.run_prep(Context(), 's', 'v1')
    assert store.read_json(root / 'manifest.json')['status'] == 'failed'
    assert next(VectorStore(root).iter_shards())[2].tolist() == [True]
    monkeypatch.setattr(pipeline, '_jsonl', original)
    pipeline.run_prep(Context(), 's', 'v1')
    assert VectorStore(root).count() == 1
    assert VectorStore(root).get(['d1'])[1].any()
    assert next(VectorStore(root).iter_shards())[2].tolist() == [False]
    assert store.read_json(root / 'stage_3.json')['embed_failed_zero_vector'] == 0


def test_doc_and_vector_shard_sizes(setup, monkeypatch):
    # Scale both boundaries together; one vector shard spans two document parts.
    monkeypatch.setattr(pipeline, 'SHARD_ROWS', 4)
    monkeypatch.setattr(pipeline, 'DOC_SHARD_ROWS', 2)
    setup([doc(str(i)) for i in range(5)])
    root = pipeline.run_prep(Context(), 's', 'v1')
    assert [len(p.read_text().splitlines()) for p in sorted((root / 'docs').glob('*.jsonl'))] == [2, 2, 1]
    assert [len(ids) for ids, _, _ in VectorStore(root).iter_shards()] == [4, 1]
    assert (root / 'vectors/shard-00001.f16').stat().st_size == 4 * 1024 * 2


@pytest.mark.parametrize('entry', ['pipeline', 'legacy_service'])
@pytest.mark.parametrize('failure_at', ['factory', 'embed'])
def test_unconnected_exports_before_embedding(setup, monkeypatch, data_dir, entry, failure_at):
    from app.jobs.manager import job_manager
    from app.services import preprocessing
    from app.vectors.embedder import EmbedderUnconnected

    setup([doc('one'), doc('two')], {'embedder': 'voyage'})
    monkeypatch.setattr(settings, 'embed_backend', 'voyage')
    monkeypatch.setattr(pipeline, 'SHARD_ROWS', 1)
    identity = Embedder()
    identity.name = 'voyage'
    root = data_dir / 'derived/s/c1' / prep_key('c1', PrepConfig(embedder='voyage'), identity)
    exported = []
    original_save = preprocessing.save_jsonl

    def save(path, documents):
        assert len(rows(root, 'docs')) == len(rows(root, 'tokens')) == 2
        assert VectorStore(root).count() == 0
        exported.extend(documents)
        original_save(path, documents)

    def unconnected():
        raise EmbedderUnconnected('not configured')

    def embed(texts):
        assert len(exported) == 2
        raise EmbedderUnconnected('not configured')

    identity.embed = embed
    monkeypatch.setattr(preprocessing, 'save_jsonl', save)
    monkeypatch.setattr(pipeline, 'get_embedder', unconnected if failure_at == 'factory' else lambda: identity)
    if entry == 'pipeline':
        with pytest.raises(EmbedderUnconnected):
            pipeline.run_prep(Context(), 's', 'v1')
    else:
        preprocessing.preprocess_data({'sid': 's'})
        status = job_manager.get('preprocess', 's')
        assert status['status'] == 'done'
        assert status['embedding'] == 'unconnected'
        assert status['original'] == status['filtered'] == 2
    assert [d['doc_id'] for d in exported] == ['one', 'two']
    assert all({'desc', 'cafe', 'link'} <= d.keys() for d in exported)
    manifest = store.read_json(root / 'manifest.json')
    assert manifest['status'] == 'failed' and manifest['compatWritten']
    assert (data_dir / manifest['compatRef']).exists()
    assert not list((root / 'vectors').glob('*.f16'))
    assert VectorStore(root).count() == 0
    assert store.load_session('s')['prep'].get('status') != 'done'


def test_old_unfinalized_snapshot_rebuilt_with_current_documents(setup, data_dir):
    setup([doc('old')])
    root = pipeline.run_prep(Context(), 's', 'v1')
    manifest = store.read_json(root / 'manifest.json')
    manifest.pop('collectionFinalized')
    store.write_json(root / 'manifest.json', manifest)
    source = data_dir / 'crawl/s/collections/c1/docs/shard-0001.jsonl'
    source.write_text(json.dumps(doc('new')) + '\n')
    assert pipeline.run_prep(Context(), 's', 'v1') == root
    assert [d['doc_id'] for d in rows(root, 'docs')] == ['new']
    assert VectorStore(root).get(['old'])[0] == []
    assert VectorStore(root).get(['new'])[0] == ['new']
    assert store.read_json(root / 'manifest.json')['collectionFinalized'] is True
