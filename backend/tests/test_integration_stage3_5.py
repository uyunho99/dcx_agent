"""Offline collection → preparation → human review → training → clustering."""
import json
from contextlib import closing
from app.crawl.queue import CrawlQueue
from pathlib import Path
import socket
from types import SimpleNamespace

import httpx
import numpy as np
import pytest
import torch

from app.config import settings
from app.context import store, versions
from app.crawl.ratelimit import ChannelLimiter
from app.label import judge, jev, rule
from app.label.overview import caches_for, labels_for
from app.prep import pipeline
from app.routers import training_v2
from app.vectors.embedder import FakeEmbedder
from app.vectors.store import VectorStore
from app.work import runner
from tests.fakes.fake_jev import FakeJev


class Context:
    def __init__(self, sid, version='v1', args=None):
        self.sid, self.version, self.args = sid, version, args or {}
        self.run_id = 'offline-' + self.args.get('labeler', 'worker')
    def heartbeat(self, *args):
        pass
    def should_stop(self):
        return False
    def should_pause(self):
        return False


@pytest.fixture
def flow(client, data_dir, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('External network is forbidden')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(settings, 'embed_backend', 'fake')
    monkeypatch.setattr(settings, 'audit_first', 2)
    monkeypatch.setattr(settings, 'audit_size', 2)
    monkeypatch.setattr(settings, 'audit_every', 10000)
    monkeypatch.setattr(settings, 'jev_api_keys', ['offline'])
    monkeypatch.setattr(settings, 'label_gpt_backend', 'codex_exec')
    monkeypatch.setattr(settings, 'codex_bin', str(Path(__file__).parent / 'fakes/fake_codex.py'))
    monkeypatch.setattr(ChannelLimiter, 'wait_start', lambda _: None)
    jev.reset_limiter_pool()
    calls, launches, embeddings = [], [], []
    fake = FakeJev()
    def handle(request):
        calls.append(request.headers['Idempotency-Key'])
        response = fake(request).json()
        # Half agree with fake codex (core); half force a real mismatch queue.
        positive = int(request.headers['Idempotency-Key'].split(':')[0][1:]) % 2 == 0
        for name, value in response['answers'].items():
            if value['type'] == 'noul':
                value['noul'] = float(positive)
            else:
                choice = next(iter(value['probabilities']))
                value.update(choice=choice, probabilities={k: float(k == choice) for k in value['probabilities']})
        return httpx.Response(200, json=response)
    real_client = jev.JevClient
    monkeypatch.setattr(judge, 'JevClient', lambda keys, model: real_client(keys, model, transport=httpx.MockTransport(handle)))
    embedder = FakeEmbedder()
    real_embed = embedder.embed
    def embed(texts):
        embeddings.append(list(texts))
        return real_embed(texts)
    monkeypatch.setattr(embedder, 'embed', embed)
    monkeypatch.setattr(pipeline, 'get_embedder', lambda: embedder)
    def launch(sid, version, kind, args):
        launches.append((kind, args))
        return {'runId': f'{kind}-{len(launches)}', 'state': 'running', 'progress': 0}
    monkeypatch.setattr(runner, 'start', launch)
    sid = 'integration'
    source = data_dir / 'crawl' / sid / 'collections/c1'
    store.write_json(source / 'manifest.json', {'parent': None})
    with closing(CrawlQueue(source / 'queue.sqlite')) as queue:
        queue.finish_run(queue.register_run('detail'), 'done')
    docs = [dict(doc_id=f'd{i:03}', title=f'경험 {i}', body=f'충분히 긴 사용 경험 본문입니다 {i}',
                 source='naver_cafe', channel='naver_cafe', comments=[]) for i in range(40)]
    store.atomic_write(source / 'docs/shard-0001.jsonl', ''.join(json.dumps(d) + '\n' for d in docs))
    store.update_session(sid, {'schemaVersion': 2, 'collectionId': 'c1', 'prep': {'config': {'embedder': 'fake'}}})
    data = store.load_session(sid)
    data['projectContext'] = {'oneLiner': '사용 경험'}
    store.write_json(store.session_dir(sid) / 'session.json', data)
    root = pipeline.run_prep(Context(sid), sid, 'v1')
    assert len(embeddings) == 1
    assert client.post(f'/label/{sid}/start').status_code == 200
    for name in ('jev', 'gpt'):
        judge.run_worker(Context(sid, args={'labeler': name}))
    assert len(calls) == 40
    assert list((data_dir / 'llm_runs').glob('*/invocations'))
    yield SimpleNamespace(sid=sid, root=root, calls=calls, embeddings=embeddings, launches=launches)
    jev.reset_limiter_pool()


def fixed_tags(level='core'):
    return dict(anchor=level != 'non', situation=level == 'core',
                sem={key: int(level == 'core' or (level == 'supporting' and key == 'sense')) for key in rule.SEM},
                signal='pain' if level != 'non' else None, reason_code='other' if level == 'non' else None)


def test_end_to_end_fixture(flow, client, data_dir, monkeypatch):
    from app.services import clustering
    from app.jobs.manager import job_manager
    sid = flow.sid
    reviewed = 0
    while (item := client.get(f'/label/{sid}/next').json()['item']):
        level = ('core', 'supporting', 'non')[reviewed % 3]
        response = client.post(f'/label/{sid}/submit', json=dict(doc_id=item['doc_id'],
            labeler='fixed-human', mode='escalate', tags=fixed_tags(level)))
        assert response.status_code == 200, response.text
        reviewed += 1
    assert reviewed == 20
    audited = 0
    while (item := client.get(f'/label/{sid}/next?mode=audit').json()['item']):
        assert item['round'] == 1
        response = client.post(f'/label/{sid}/submit', json=dict(doc_id=item['doc_id'],
            labeler='fixed-human', mode='audit', round=1, tags=fixed_tags()))
        assert response.status_code == 200, response.text
        audited += 1
    assert audited == 2
    labels = labels_for(sid, store.load_session(sid))
    with labels._db() as db:
        assert db.execute('SELECT count(DISTINCT round) FROM audit_set').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM human').fetchone()[0] == reviewed + audited
    real_train = training_v2.train_ensemble
    monkeypatch.setattr(training_v2, 'train_ensemble', lambda X, T: real_train(X, T, max_epochs=1))
    threads = torch.get_num_threads()
    try:
        torch.set_num_threads(1)
        assert client.post(f'/train/{sid}').status_code == 200
        training_v2.run_worker(Context(sid))
        from app.model import infer
        infer.run_worker(Context(sid))
    finally:
        torch.set_num_threads(threads)
    assert store.load_session(sid)['training']['modelId']
    assert store.load_session(sid)['training']['inferStatus'] == 'done'
    response = client.post(f'/train/{sid}/export', json={})
    assert response.status_code == 200, response.text
    rows = [json.loads(line) for line in (data_dir / response.json()['exportRef']).read_text().splitlines()]
    assert {r['evidence_level_pred'] for r in rows} == {'core', 'supporting'}
    assert len(rows) < 40
    api_calls = []
    def forbidden_embedding(*args):
        api_calls.append(args)
        raise AssertionError('Clustering must reuse vectors')
    monkeypatch.setattr(clustering, 'get_embeddings', forbidden_embedding)
    observed = []
    real_fit = clustering.KMeans.fit_predict
    def fit(self, X, *args, **kwargs):
        observed.append(X.copy())
        return real_fit(self, X, *args, **kwargs)
    monkeypatch.setattr(clustering.KMeans, 'fit_predict', fit)
    clustering.run_clustering({'sid': sid, 'num_clusters': 2})
    assert job_manager.get('cluster', sid)['status'] == 'done'
    assert api_calls == [] and len(flow.embeddings) == 1
    ids, vectors = VectorStore(flow.root).get([r['doc_id'] for r in rows])
    by_id = dict(zip(ids, vectors))
    np.testing.assert_array_equal(observed[0], [by_id[r['doc_id']] for r in rows])
    clustered = [json.loads(line) for path in (data_dir / 'clusters' / sid).glob('*.jsonl') for line in path.read_text().splitlines()]
    assert {r['doc_id'] for r in clustered} == {r['doc_id'] for r in rows}


def test_restart_stage4_reuses_cache(flow, client, monkeypatch):
    from app.crawl import control
    monkeypatch.setattr(control, 'phase_state', lambda *args: 'done')
    sid = flow.sid
    old_caches = {k: v.path for k, v in caches_for(sid, store.load_session(sid)).items()}
    item = client.get(f'/label/{sid}/next').json()['item']
    assert client.post(f'/label/{sid}/submit', json=dict(doc_id=item['doc_id'], labeler='fixed-human',
        mode='escalate', tags=fixed_tags())).status_code == 200
    versions.create_version(sid, 'v1', 'stage4', 'review again')
    assert store.load_session(sid)['labeling']['started'] is False
    assert store.load_session(sid)['labeling']['restartMessage'] == '이 라벨은 v1 기준입니다. LLM 판정은 재사용하고 사람 검수만 다시 합니다.'
    old_labels = labels_for(sid, versions._data(sid, 'v1'))
    assert old_labels.get(item['doc_id']).source == 'human'
    with labels_for(sid, store.load_session(sid))._db() as db:
        assert db.execute('SELECT count(*) FROM stale_final').fetchone()[0] == 40
        assert db.execute('SELECT count(*) FROM final').fetchone()[0] == 0
    assert client.post(f'/label/{sid}/mode', json={'mode': 'llm'}).status_code == 200
    assert client.post(f'/label/{sid}/start').status_code == 200
    invocations = {p: p.read_bytes() for p in (Path(settings.local_data_dir) / 'llm_runs').glob('*/invocations')}
    flow.calls.clear()
    for name in ('jev', 'gpt'):
        judge.run_worker(Context(sid, 'v2', {'labeler': name}))
    assert flow.calls == []
    assert invocations == {p: p.read_bytes() for p in (Path(settings.local_data_dir) / 'llm_runs').glob('*/invocations')}
    assert old_caches == {k: v.path for k, v in caches_for(sid, store.load_session(sid)).items()}
    labels = labels_for(sid, store.load_session(sid))
    with labels._db() as db:
        assert db.execute('SELECT count(*) FROM human').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM final').fetchone()[0] == 40
    assert client.get(f'/label/{sid}/next').json()['item'] is not None


def test_restart_stage3_reuses_preparation(flow, monkeypatch):
    from app.crawl import control
    monkeypatch.setattr(control, 'phase_state', lambda *args: 'done')
    versions.create_version(flow.sid, 'v1', 'stage3', 'same rules')
    assert store.load_session(flow.sid)['prep']['status'] == 'stale'
    assert pipeline.run_prep(Context(flow.sid, 'v2'), flow.sid, 'v2') == flow.root
    assert len(flow.embeddings) == 1
    assert store.load_session(flow.sid)['prep']['status'] == 'done'
    metrics = store.read_json(flow.root / 'stage_3.json')
    assert versions.compare(flow.sid, 'v1', 'v2', 'stage3')['stage_3'] == {'before': metrics, 'after': metrics}
