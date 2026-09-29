"""Offline stage 0–2 and legacy downstream compatibility contracts."""
import importlib.util
import json
from pathlib import Path
import socket
import time
from types import SimpleNamespace

import numpy as np
import pytest

from app.config import settings
from app.context import store
from app.crawl import control, worker
from app.crawl.writer import DocWriter
from app.external.base import integration_status
from app.jobs.manager import job_manager
from app.keywords import rounds
from app.keywords.prompts import MIN_COUNT
from app.llm.fake import FakeBackend
from app.services.preprocessing import preprocess_data
from app.services.s3 import load_data, save_jsonl

CTX = dict(bk='에어컨', oneLiner='시원한 공기', researchQuestion={'text': '냉방 경험은?'},
           projectType={'choice': 'new'}, analysisGoal={'choice': 'needs'}, keyMetrics=['만족'],
           constraints=[], positioning={'price': 'value', 'market': 'new'}, channels=['fixture'],
           productCategory={'l1': '가전', 'source': 'user'})
KEY_FIELDS = [name for name in type(settings).model_fields
              if 'key' in name or 'secret' in name or name in ('naver_client_id', 'searchad_customer_id')]


@pytest.fixture
def offline(data_dir, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError('Network is forbidden')
    monkeypatch.setattr(socket.socket, 'connect', no_network)
    for name in KEY_FIELDS:
        monkeypatch.setattr(settings, name, '')
    monkeypatch.setattr(settings, 'author_salt_path', str(data_dir / '.author_salt'))
    monkeypatch.setattr(settings, 'enable_fixture_channel', True)
    corpus = data_dir / 'corpus.csv'
    spec = importlib.util.spec_from_file_location('make_corpus', Path(__file__).parent / 'fixtures/make_corpus.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.write_corpus(corpus, 200)
    monkeypatch.setattr(settings, 'fixture_corpus_path', str(corpus))
    fake_dir = data_dir / 'fake_llm'
    fake_dir.mkdir()
    responses = {'category_suggest': {'l1': '가전', 'l2': '계절가전', 'l3': '에어컨'}}
    for n in range(1, 5):
        responses[f'kw_round_{n}'] = {'keywords': [
            {'kw': f'냉방{n}단어{i}', 'axis': 'physical', 'sub': 'space', 'why': '상황'}
            for i in range(MIN_COUNT[n])]}
    for name, response in responses.items():
        (fake_dir / f'{name}.json').write_text(json.dumps(response), encoding='utf-8')
    monkeypatch.setattr(FakeBackend, 'fixture_dir', fake_dir)
    monkeypatch.setattr(settings, 'llm_backend_overrides', {'kw_round_*': 'fake', 'category_suggest': 'fake'})
    monkeypatch.setattr(rounds, 'execute', lambda fn: fn())
    # Defer execution until API session/collection locks are released.
    pending = []
    def spawn(sid, root, queue, kind, snapshot=None):
        pending.append((sid, root, kind, snapshot))
        return {'collectionId': root.name, 'kind': kind, 'status': 'running', 'pid': 0}
    monkeypatch.setattr(control, '_spawn', spawn)
    return pending


def full_flow(client, offline):
    responses = []
    def request(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        responses.append(response.json())
        assert response.status_code < 300, response.text
        return response.json()
    def work():
        sid, root, kind, snapshot = offline.pop(0)
        if kind == 'list':
            worker.run_list(sid, collection=root)
        else:
            worker.run_detail(sid, snapshot, collection=root, backoff_s=0)
    category = request('POST', '/context/category-suggest', json={'bk': CTX['bk'], 'oneLiner': CTX['oneLiner']})
    sid = request('POST', '/context', json={**CTX, 'productCategory': category})['sid']
    for n in range(1, 5):
        request('POST', f'/keywords/{sid}/rounds/{n}')
        state = request('GET', f'/keywords/{sid}/rounds/{n}')
        assert state['status'] == 'done' and len(state['keywords']) == MIN_COUNT[n]
        assert state['below_min'] is None
        request('POST', f'/keywords/{sid}/rounds/{n}/commit', json={
            'gen': state['gen'], 'decisions': [{'id': k['id'], 'status': 'approved'} for k in state['keywords']]})
    request('PUT', f'/crawl/{sid}/config', json={
        'channels': ['fixture'], 'dateFrom': None, 'dateTo': None,
        'perChannel': {'fixture': {'concurrency': 4, 'min_interval_s': 0}}})
    request('POST', f'/crawl/{sid}/list')
    work()
    status = request('GET', f'/crawl/{sid}/status')
    assert status['gate'] and status['status'] == 'done'
    request('PUT', f'/crawl/{sid}/gate', json={'exclusions': []})
    request('POST', f'/crawl/{sid}/detail', json={'snapshot_id': status['snapshot_id']})
    work()
    status = request('GET', f'/crawl/{sid}/status')
    assert status['report']['totals']['doc_count'] == 200
    assert request('POST', '/preprocess', json={'sid': sid}) == {'sid': sid, 'status': 'started'}
    deadline = time.monotonic() + 5
    while True:
        status = request('GET', f'/preprocess-status/{sid}')
        if status['status'] != 'running' or time.monotonic() > deadline:
            break
        time.sleep(.01)
    assert status['status'] == 'done', status
    docs = load_data(f'preprocessed/{sid}/')
    assert len(docs) == 200
    assert all(d['desc'] == d['body'] + '\n' and d['cafe'] == '개발용 샘플' and d['link'] == d['url'] for d in docs)
    return sid, docs, responses


def test_end_to_end_0_to_preprocess(client, offline):
    full_flow(client, offline)


def test_no_api_keys_full_run(client, offline):
    _, _, responses = full_flow(client, offline)
    response = client.get('/integrations')
    assert response.status_code == 200
    responses.append(response.json())
    assert response.json() == [entry.model_dump() for entry in integration_status()]
    assert all(not entry['connected'] for entry in response.json())
    serialized = json.dumps(responses)
    assert all(not getattr(settings, name) or getattr(settings, name) not in serialized for name in KEY_FIELDS)


def test_integrations_never_exposes_configured_secrets(client, offline, monkeypatch):
    for i, name in enumerate(KEY_FIELDS):
        monkeypatch.setattr(settings, name, f'SENTINEL_KEY_{i}_123')
    from app.routers import integrations
    calls = []
    def status():
        calls.append(True)
        return integration_status()
    monkeypatch.setattr(integrations, 'integration_status', status)
    response = client.get('/integrations')
    assert calls == [True]
    assert response.json() == [entry.model_dump() for entry in integration_status()]
    assert all(getattr(settings, name) not in response.text for name in KEY_FIELDS)


def test_legacy_session_preprocess_still_reads_old_crawl(data_dir):
    doc = {'title': '오래된 사용 후기', 'desc': '충분히 긴 설명을 가진 기존 데이터', 'cafe': '카페', 'link': 'old'}
    save_jsonl('crawl/legacy/part.jsonl', [doc, doc])
    preprocess_data({'sid': 'legacy'})
    assert load_data('preprocessed/legacy/') == [{**doc, 'idx': 0}]


def put_collection(data_dir, sid, cid, parent, docs):
    root = data_dir / 'crawl' / sid / 'collections' / cid
    store.write_json(root / 'manifest.json', {'id': cid, 'parent': parent})
    writer = DocWriter(root / 'docs')
    try:
        for doc in docs:
            writer.write(doc)
    finally:
        writer.close()


def document(doc_id, **kwargs):
    return dict(doc_id=doc_id, source='youtube', title='', body='충분히 긴 본문 내용입니다', comments=[{'text': '댓글 내용'}],
                src_meta={}, url=f'https://example.test/{doc_id}', fetch_level='full', **kwargs)


def test_preprocess_reads_collection_chain(client, data_dir):
    sid = client.post('/context', json=CTX).json()['sid']
    parent = document('shared')
    child = {**parent, 'body': '자식 수집본의 본문 내용입니다', 'src_meta': {'cafe': '지정 카페'}}
    put_collection(data_dir, sid, 'c1', None, [parent, document('parent')])
    store.update_session(sid, {'collectionId': 'c1'})
    assert client.post(f'/sessions/{sid}/versions', json={'from': 'v1', 'restartFrom': 'stage2'}).status_code == 201
    store.update_session(sid, {'collectionId': 'c2'})
    put_collection(data_dir, sid, 'c2', 'c1', [child, document('child'), child])
    put_collection(data_dir, sid, 'c3', None, [document('unrelated')])
    preprocess_data({'sid': sid})
    docs = {d['doc_id']: d for d in load_data(f'preprocessed/{sid}/')}
    assert set(docs) == {'shared', 'parent', 'child'}
    assert docs['shared']['desc'] == child['body'] + '\n댓글 내용'
    assert docs['shared']['cafe'] == '지정 카페'
    assert docs['parent']['cafe'] == '유튜브'
    assert all(docs['shared'][k] == v for k, v in child.items())
    assert job_manager.get('preprocess', sid)['filtered'] == 3


def test_quality_and_desc_limit(data_dir):
    docs = [document('full'), {**document('short'), 'body': '짧음'},
            {**document('long'), 'body': '긴' * 4100},
            {**document('snippet_ok'), 'fetch_level': 'snippet', 'title': '다섯글자제목', 'body': '', 'snippet': '충분히 긴 설명 내용입니다'},
            {**document('snippet_bad_title'), 'fetch_level': 'snippet', 'title': '짧음', 'snippet': '충분히 긴 설명 내용입니다'},
            {**document('snippet_bad_desc'), 'fetch_level': 'snippet', 'title': '다섯글자제목', 'body': '', 'snippet': '짧음'}]
    put_collection(data_dir, 'quality', 'c1', None, docs)
    store.update_session('quality', {'collectionId': 'c1'})
    preprocess_data({'sid': 'quality'})
    result = {d['doc_id']: d for d in load_data('preprocessed/quality/')}
    assert set(result) == {'full', 'long', 'snippet_ok'}
    assert result['long']['desc'] == '긴' * 4000


def test_downstream_clustering_reads_compat_fields(client, offline, monkeypatch):
    from app.services import clustering
    sid, docs, _ = full_flow(client, offline)
    def embeddings(texts):
        assert all(d['desc'] in text for d, text in zip(docs, texts))
        return np.random.default_rng(42).normal(size=(len(texts), 8)).tolist()
    monkeypatch.setattr(clustering, 'get_embeddings', embeddings)
    from threadpoolctl import threadpool_limits
    with threadpool_limits(limits=1):
        clustering.run_clustering({'sid': sid, 'num_clusters': 3})
    status = job_manager.get('cluster', sid)
    assert status['status'] == 'done', status
    assert status['total'] == 200
    assert all(s['desc'] and s['cafe'] for c in status['clusters'].values() for s in c['samples'])


@pytest.mark.parametrize('module,endpoint,service', [
    ('training', '/train', 'train_models'), ('personas', '/persona', 'run_persona'),
    ('clustering', '/cluster', 'run_clustering'), ('clustering', '/cluster-refine', 'refine_clusters')])
def test_downstream_context_fallback(client, monkeypatch, module, endpoint, service):
    import importlib
    router = importlib.import_module(f'app.routers.{module}')
    calls = []
    monkeypatch.setattr(router, service, lambda config: calls.append(config) or {'status': 'done'})
    class InlineThread:
        def __init__(self, target, **kwargs):
            self.target = target
        def start(self):
            self.target()
    monkeypatch.setattr(router, 'threading', SimpleNamespace(Thread=InlineThread))
    sid = client.post('/context', json=CTX).json()['sid']
    assert client.post(endpoint, json={'sid': sid}).status_code == 200
    assert calls[-1]['bk'] == CTX['bk']
    assert calls[-1]['problemDef'] == CTX['researchQuestion']['text']
    if module != 'clustering':
        client.post(endpoint, json={'sid': sid, 'bk': 'explicit', 'problemDef': 'explicit question'})
        assert calls[-1]['bk'] == 'explicit' and calls[-1]['problemDef'] == 'explicit question'
