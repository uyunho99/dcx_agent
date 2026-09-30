import json
from types import SimpleNamespace
import numpy as np
import pytest

from app.config import settings
from app.context import store
from app.label import rule
from app.label.overview import labels_for, caches_for
from app.model import infer, monitor
from app.work import worker
from .test_registry import save_model, EMBEDDER


def prepared(data_dir, n=3):
    sid = 'modeltest'
    store.update_session(sid, {'schemaVersion': 2, 'prep': {'status': 'done',
        'derivedRef': {'collectionId': 'c1', 'prepKey': 'p_123456789abc'}}})
    data = store.load_session(sid)
    data['projectContext'] = {'oneLiner': 'definition', 'bk': 'test'}
    store.write_json(store.session_dir(sid) / 'session.json', data)
    root = data_dir / f'derived/{sid}/c1/p_123456789abc'
    (root / 'docs').mkdir(parents=True)
    docs = [dict(doc_id=f'd{i}', title=f'title {i}', body='body text', channel='naver_cafe', cafe='cafe', kw='kw') for i in range(n)]
    (root / 'docs/part.jsonl').write_text('\n'.join(map(json.dumps, docs)))
    store.write_json(root / 'manifest.json', {'embedder': EMBEDDER})
    from app.vectors.store import VectorStore
    VectorStore(root).write_shard([d['doc_id'] for d in docs], np.ones((n, 1024)), [False] * n)
    return sid, docs


def context(sid, kind='infer', args=None):
    return SimpleNamespace(sid=sid, version='v1', kind=kind, args=args or {}, run_id='test',
        heartbeat=lambda *a: None, should_stop=lambda: False)


def test_model_mode_zero_llm_calls(client, data_dir, monkeypatch):
    sid, docs = prepared(data_dir)
    mid = save_model()
    monkeypatch.setattr(settings, 'monitor_rate', 0)
    def forbidden(*a, **kw):
        pytest.fail('model mode must make zero LLM calls when monitoring is disabled')
    monkeypatch.setattr('app.label.jev.JevClient.judge', forbidden)
    monkeypatch.setattr('app.label.gpt.judge_batch', forbidden)
    launched = []
    def launch(s, v, kind, args):
        launched.append((kind, args))
        return dict(runId='infer1', state='running')
    monkeypatch.setattr('app.routers.labeling_v2.runner.start', launch)
    assert client.post(f'/label/{sid}/mode', json=dict(mode='model', modelId=mid)).status_code == 200
    assert client.post(f'/label/{sid}/start').status_code == 200
    assert [k for k, _ in launched] == ['infer']
    worker.KINDS['infer'](context(sid, args=launched[0][1]))
    view = client.get(f'/label/{sid}/overview').json()
    assert view['accepted'] == len(docs) and view['queue']['total'] == 0
    response = client.post(f'/train/{sid}/export', json={})
    assert response.status_code == 200, response.text
    report = json.loads((store.session_dir(sid) / 'stage_5.json').read_text())
    assert report['mode'] == 'model' and report['model']['modelId'] == mid
    assert report['monitorDivergence'] is None


def test_model_disagree_routed(client, data_dir, monkeypatch):
    sid, _ = prepared(data_dir)
    mid = save_model()
    store.update_session(sid, {'labeling': {'mode': 'model', 'modelId': mid}})
    pred = infer.from_tag_probs(dict.fromkeys(rule.GRADE_FIELDS, .99),
        [dict.fromkeys(rule.GRADE_FIELDS, .99), dict.fromkeys(rule.GRADE_FIELDS, .01)])
    monkeypatch.setattr(infer, 'predict', lambda model, X: [pred] * len(X))
    monkeypatch.setattr(settings, 'monitor_rate', 0)
    infer.run_worker(context(sid))
    for _ in range(2):
        view = client.get(f'/label/{sid}/overview').json()
        assert view['queue']['byReason']['model_disagree'] == 3
    item = client.get(f'/label/{sid}/next').json()['item']
    assert item['reason'] == 'model_disagree' and item['document']['title']
    assert client.post(f'/train/{sid}/export', json={}).status_code == 409
    tags = dict(anchor=False, situation=False, sem=dict.fromkeys(rule.SEM, 0))
    assert client.post(f'/label/{sid}/submit', json=dict(doc_id=item['doc_id'], labeler='person', mode='escalate', tags=tags)).status_code == 200
    infer.run_worker(context(sid))
    assert labels_for(sid, store.load_session(sid)).get(item['doc_id']).source == 'human'


def test_monitor_divergence_warn():
    result = monitor.divergence(['core'] * 20, ['non'] * 4 + ['core'] * 16)
    assert result['n'] == 20 and result['monitorDivergence'] == .2 and result['warning']
    assert monitor.divergence(['core'] * 20, ['non'] * 3 + ['core'] * 17)['warning'] is None


def test_model_selection_rejects_mismatch(client, data_dir):
    sid, _ = prepared(data_dir)
    mid = save_model()
    root = data_dir / f'derived/{sid}/c1/p_123456789abc'
    store.write_json(root / 'manifest.json', {'embedder': {**EMBEDDER, 'name': 'voyage'}})
    response = client.post(f'/label/{sid}/mode', json=dict(mode='model', modelId=mid))
    assert response.status_code == 409


def test_monitor_uses_only_sample_and_reuses_judge_caches(client, data_dir, monkeypatch):
    from app.label.gpt import GptVote
    from app.label.schema import JevVote
    sid, _ = prepared(data_dir, 100)
    mid = save_model()
    store.update_session(sid, {'labeling': {'mode': 'model', 'modelId': mid}})
    monkeypatch.setattr(settings, 'monitor_rate', 0)
    infer.run_worker(context(sid))
    monkeypatch.setattr(settings, 'monitor_rate', .01)
    calls = []
    class Judge:
        def __init__(self, *a):
            pass
        def judge(self, doc, one_liner, **kw):
            calls.append(('jev', doc['doc_id']))
            assert one_liner == 'definition' and doc['doc_id'] in kw['idempotency_key']
            return JevVote(probs=dict.fromkeys(rule.GRADE_FIELDS, 0.), reason_probs={'other': 1.}, model='fake')
        def close(self):
            pass
    def gpt(docs, one_liner, **kw):
        calls.append(('gpt', docs[0]['doc_id']))
        return {docs[0]['doc_id']: GptVote(anchor=False, situation=False, sem=dict.fromkeys(rule.SEM, 0))}, []
    monkeypatch.setattr(monitor, 'JevClient', Judge)
    monkeypatch.setattr('app.label.gpt.judge_batch', gpt)
    monitor.run_worker(context(sid, 'monitor'))
    monitor.run_worker(context(sid, 'monitor'))
    assert len(calls) == 2 and calls[0][1] == calls[1][1]
    saved = store.load_session(sid)['training']['monitor']
    assert saved['n'] == saved['sampled'] == 1 and saved['monitorDivergence'] == 1 and saved['warning']
    assert all(cache.counts()['done'] == 1 for cache in caches_for(sid, store.load_session(sid)).values())
    # Monitoring must not replace model predictions with monitor votes.
    assert client.get(f'/label/{sid}/overview').json()['accepted'] == 100
    assert labels_for(sid, store.load_session(sid)).get(calls[0][1]).source == 'model'


def test_status_after_worker_launch(client, data_dir, monkeypatch):
    sid, _ = prepared(data_dir)
    store.update_session(sid, {'training': {'runId': 'train1'}})
    monkeypatch.setattr('app.work.runner.status', lambda sid: [dict(runId='train1', kind='train', state='running')])
    response = client.get(f'/train/{sid}/status')
    assert response.status_code == 200 and len(response.json()['workers']) == 1


def test_training_rows_alignment_and_truncation(data_dir):
    from app.routers.training_v2 import training_data
    from .test_export import seed
    sid, _ = prepared(data_dir)
    seed(sid)
    data = store.load_session(sid)
    labels = labels_for(sid, data)
    cache = caches_for(sid, data)['jev']
    cache.seed(['d0', 'd1'])
    cache.put('d0', dict(probs=dict.fromkeys(rule.GRADE_FIELDS, .8), reason_probs={'other': 1.}, truncated=True))
    cache.put('d1', dict(probs=dict.fromkeys(rule.GRADE_FIELDS, .8), reason_probs={'other': 1.}, truncated=False))
    with labels._db() as db:
        tags = json.loads(db.execute("SELECT tags_json FROM final WHERE doc_id='d0'").fetchone()[0])
        db.execute("UPDATE final SET source='agreed',route='accepted',votes_json=? WHERE doc_id='d0'", (json.dumps({'gpt': tags, 'jev': dict(probs=dict.fromkeys(rule.GRADE_FIELDS, .8), reason_probs={'other': 1.}, truncated=True)}),))
        db.execute("UPDATE final SET source='agreed',route='escalated:grade_mismatch' WHERE doc_id='d1'")
    X, targets = training_data(sid, data)
    assert targets.doc_ids.tolist() == ['d0', 'd2']
    assert targets.weights.tolist() == [1, 3] and X[:, -1].tolist() == [1, 0]


def test_legacy_train_is_readonly(client, data_dir, monkeypatch):
    from app.routers import training
    from app.jobs.manager import job_manager
    sid = 'legacy_model'
    store.update_session(sid, {'training': {'status': 'done', 'scores': {'LSTM': .8}}})
    original = (store.session_dir(sid) / 'session.json').read_bytes()
    class InlineThread:
        def __init__(self, target, **kw):
            self.target = target
        def start(self):
            self.target()
    monkeypatch.setattr(training.threading, 'Thread', InlineThread)
    response = client.post('/train', json={'sid': sid})
    assert response.status_code == 200
    assert client.get(f'/train-status/{sid}').json()['scores'] == {'LSTM': .8}
    assert (store.session_dir(sid) / 'session.json').read_bytes() == original


def test_missing_vector_routes_to_human(client, data_dir, monkeypatch):
    sid, docs = prepared(data_dir)
    root = data_dir / f'derived/{sid}/c1/p_123456789abc/docs'
    (root / 'extra.jsonl').write_text(json.dumps({**docs[0], 'doc_id': 'missing'}))
    store.update_session(sid, {'labeling': {'mode': 'model', 'modelId': save_model()}})
    monkeypatch.setattr(settings, 'monitor_rate', 0)
    infer.run_worker(context(sid))
    view = client.get(f'/label/{sid}/overview').json()
    assert view['accepted'] == 3 and view['queue']['byReason']['model_uncertain'] == 1
    assert client.get(f'/label/{sid}/next').json()['item']['doc_id'] == 'missing'


def test_train_worker_and_parent_snapshot(client, data_dir, monkeypatch):
    from app.routers import training_v2
    from app.model import registry
    from .test_registry import result, EMBEDDER
    sid, docs = prepared(data_dir, 12)
    data = store.load_session(sid)
    labels = labels_for(sid, data)
    tags = dict(anchor=True, situation=True, sem=dict.fromkeys(rule.SEM, 1))
    with labels._db() as db:
        for doc in docs:
            db.execute('INSERT INTO final VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (doc['doc_id'], 'core', 1., 'human', 'audited', json.dumps(tags), None, 'pain', 'r1', 'q1', '{}', '[]', 0))
    observed = []
    def train(X, targets):
        observed.append((X.copy(), targets))
        trained = result()
        trained.doc_ids = targets.doc_ids
        return trained
    monkeypatch.setattr(training_v2, 'train_ensemble', train)
    launches = []
    monkeypatch.setattr(training_v2.runner, 'start', lambda *args: launches.append(args) or dict(runId='next', state='running'))
    training_v2.run_worker(context(sid, 'train'))
    model_id = store.load_session(sid)['training']['modelId']
    assert registry.metadata(model_id)['n'] == 12
    assert registry.metadata(model_id)['metrics']['evaluation_split'] == 'validation'
    assert registry.dataset(model_id)['weights'].tolist() == [3.] * 12
    before = (data_dir / 'models' / model_id / 'meta.json').read_bytes()
    # A subsequent version may hold only new or corrected labels; parent retains others.
    with labels._db() as db:
        db.execute("DELETE FROM final WHERE doc_id!='d0'")
    X, targets = training_v2.training_data(sid, data, parent=model_id)
    assert len(targets.doc_ids) == 12 and targets.doc_ids[-1] == 'd0'
    training_v2.run_worker(context(sid, 'train', {'parent': model_id}))
    child = store.load_session(sid)['training']['modelId']
    assert child != model_id and registry.metadata(child)['parent'] == model_id
    assert (data_dir / 'models' / model_id / 'meta.json').read_bytes() == before
    assert all(args[2] == 'infer' for args in launches)
    assert client.get(f'/models?sid={sid}').json()['models'][0]['selectable']


def test_llm_predictions_do_not_suppress_new_label_merges(client, data_dir, monkeypatch):
    from app.label.schema import JevVote
    from app.label.gpt import GptVote
    sid, _ = prepared(data_dir)
    model_id = save_model()
    store.update_session(sid, {'training': {'modelId': model_id}})
    infer.run_worker(context(sid, args={'modelId': model_id}))
    data = store.load_session(sid)
    caches = caches_for(sid, data)
    for cache in caches.values():
        cache.seed(['d0'])
    caches['jev'].put('d0', JevVote(probs=dict.fromkeys(rule.GRADE_FIELDS, .99), reason_probs={'not_non': 1.}, model='fake').model_dump())
    caches['gpt'].put('d0', GptVote(anchor=True, situation=True, sem=dict.fromkeys(rule.SEM, 1)).model_dump())
    assert client.get(f'/label/{sid}/overview').json()['accepted'] == 1
    assert labels_for(sid, data).get('d0').source == 'agreed'


def test_model_overview_reports_inference_progress(client, data_dir, monkeypatch):
    sid, _ = prepared(data_dir)
    store.update_session(sid, {'labeling': {'mode': 'model', 'started': True, 'inferRunId': 'inference'},
                               'training': {'inferRunId': 'inference'}})
    monkeypatch.setattr('app.work.runner.status', lambda sid: [dict(runId='inference', kind='infer', state='running', progress=.4, detail={})])
    view = client.get(f'/label/{sid}/overview').json()
    assert view['now']['state'] == 'running'
    assert view['progress']['infer']['progress'] == .4
    assert 'jev' not in view['progress']


def test_unchanged_model_audit_is_human_training_row(client, data_dir, monkeypatch):
    from app.label import audit
    from app.routers.training_v2 import training_data
    sid, _ = prepared(data_dir)
    store.update_session(sid, {'labeling': {'mode': 'model', 'modelId': save_model()}})
    monkeypatch.setattr(settings, 'monitor_rate', 0)
    infer.run_worker(context(sid))
    labels = labels_for(sid, store.load_session(sid))
    audit.maybe_new_round(labels, 1000)
    item = client.get(f'/label/{sid}/next?mode=audit').json()['item']
    label = labels.get(item['doc_id'])
    tags = {k: getattr(label, k) for k in ('anchor', 'sem', 'situation', 'reason_code', 'signal')}
    assert client.post(f'/label/{sid}/submit', json=dict(doc_id=item['doc_id'], mode='audit',
        round=item['round'], labeler='person', tags=tags)).status_code == 200
    assert labels.get(item['doc_id']).source == 'human'
    _, targets = training_data(sid, store.load_session(sid))
    assert targets.doc_ids.tolist() == [item['doc_id']] and targets.weights.tolist() == [3.]
