"""Whole-branch regressions for final-fix1 (R-106 through R-110 and minors)."""
import json
import os
import time
from unittest.mock import Mock

import httpx
import numpy as np
import pytest
import torch

from app.config import settings
from app.context import store, versions
from app.label import rule
from app.label.votes import VoteCache
from app.work import runner, worker
from app.work.status import transaction
from tests.context.test_api import CTX, create
from tests.model.test_model_mode import prepared, context
from tests.model.test_registry import save_model
from tests.model.test_train import row
from tests.label.test_judge import setup_judge, cache_for, Context

LOCK_MESSAGE = '라벨링을 시작한 뒤에는 이 버전에서 바꿀 수 없습니다. 새 버전에서 다시 하세요.'


def register(sid, run_id, kind='infer', state='running'):
    with transaction(sid) as db:
        db.execute('INSERT INTO runs(run_id,version,kind,args_json,pid,state,heartbeat_at,started_at) VALUES (?,?,?,?,?,?,?,?)',
                   (run_id, 'v1', kind, '{}', os.getpid(), state, time.time(), time.time()))


@pytest.mark.parametrize('method', ['put', 'patch'])
def test_r106_context_lock(client, method):
    sid = create(client)
    store.update_session(sid, {'labeling': {'started': True}})
    before = store.load_session(sid)
    response = getattr(client, method)(f'/context/{sid}', json={**CTX, 'oneLiner': 'changed'})
    assert response.status_code == 409
    assert response.json()['status'] == 'error'
    assert response.json()['error']['message'] == LOCK_MESSAGE
    assert store.load_session(sid) == before
    response = getattr(client, method)(f'/context/{sid}', json={**CTX, 'researchQuestion': {'text': 'allowed'}})
    assert response.status_code == 200
    versions.create_version(sid, 'v1', 'stage3', '')
    assert getattr(client, method)(f'/context/{sid}', json={**CTX, 'oneLiner': 'new version'}).status_code == 200


def test_r106_prep_lock(client):
    sid = create(client)
    store.update_session(sid, {'labeling': {'started': True}})
    before = store.load_session(sid)
    response = client.put(f'/prep/{sid}/config', json={})
    assert response.status_code == 409
    assert response.json()['error']['message'] == LOCK_MESSAGE
    assert store.load_session(sid) == before


def test_r106_targets_use_final_votes_without_cache():
    from app.model.train import build_targets
    r = row(source='agreed', anchor=False)
    votes = json.loads(r['votes_json'])
    votes['jev'] = dict(probs=dict.fromkeys(rule.GRADE_FIELDS, .2), reason_probs={'ad': .8, 'other': .2})
    r['votes_json'] = json.dumps(votes)
    t = build_targets([r], {})
    assert t.values['anchor'][0, 0] == pytest.approx(.1)
    assert t.values['reason'][0].tolist() == pytest.approx([.4, 0, 0, .6])
    # A newer cache must not silently change the historical training targets.
    newer = {'0': {'probs': dict.fromkeys(rule.GRADE_FIELDS, .9)}}
    assert torch.equal(t.values['anchor'], build_targets([r], newer).values['anchor'])


def test_r107_preserves_known_and_embeds_only_changed(client, monkeypatch):
    from app.known import store as known
    monkeypatch.setattr(settings, 'embed_backend', 'fake')
    sid = client.post('/context', json={**CTX, 'knownInsights': ['keep', 'edit', 'remove']}).json()['sid']
    original = known.list_known(sid)[0].model_dump(by_alias=True)
    extras = [dict(id=origin, type='statement' if origin != 'rag' else 'doc', text=origin,
                   doc_id='d0' if origin == 'rag' else None, **{'from': origin}, vectorRow=None)
              for origin in ['drawer', 'rag', 'prev_session']]
    store.update_session(sid, {'knownInsights': store.load_session(sid)['knownInsights'] + extras})
    embedder = Mock()
    embedder.embed.side_effect = lambda texts: np.ones((len(texts), settings.embed_dim))
    monkeypatch.setattr(known, 'get_embedder', lambda: embedder)
    body = {**CTX, 'knownInsights': ['edited', 'keep', 'added']}
    assert client.put(f'/context/{sid}', json=body).status_code == 200
    items = store.load_session(sid)['knownInsights']
    assert all(item in items for item in extras)
    assert original in items
    embedder.embed.assert_called_once_with(['edited', 'added'])
    assert len({i['id'] for i in items}) == len(items)
    assert all(i['vectorRow'] is not None for i in items if i['from'] == 'stage0')
    assert client.put(f'/context/{sid}', json=body).status_code == 200
    assert embedder.embed.call_count == 1


@pytest.mark.parametrize('failure', ['jev', 'gpt', 'store', 'transport'])
def test_r108_monitor_records_sample_errors_and_finishes(client, data_dir, monkeypatch, failure):
    from app.model import infer, monitor
    from app.label.jev import JevError
    from app.label.gpt import LabelerPaused
    sid, _ = prepared(data_dir)
    mid = save_model()
    store.update_session(sid, {'labeling': {'mode': 'model', 'modelId': mid}})
    monkeypatch.setattr(settings, 'monitor_rate', 0)
    infer.run_worker(context(sid))
    monkeypatch.setattr(settings, 'monitor_rate', 1)
    errors = {'jev': JevError('unconnected', 'secret provider detail'),
              'gpt': LabelerPaused('secret provider detail'),
              'store': store.StoreError('secret provider detail'),
              'transport': httpx.ConnectError('secret provider detail')}
    from app.label.schema import JevVote
    from app.label.gpt import GptVote
    original_claim = monitor._claim
    def claim(cache, doc_id, run_id):
        if failure == 'store' and doc_id == 'd0':
            raise errors[failure]
        return original_claim(cache, doc_id, run_id)
    class Judge:
        def __init__(self, *args):
            pass
        def judge(self, doc, *args, **kwargs):
            if failure in ('jev', 'transport') and doc['doc_id'] == 'd0':
                raise errors[failure]
            return JevVote(probs=dict.fromkeys(rule.GRADE_FIELDS, .99), reason_probs={'not_non': 1}, model='fake')
        def close(self):
            pass
    def gpt(docs, *args, **kwargs):
        doc_id = docs[0]['doc_id']
        if failure == 'gpt' and doc_id == 'd0':
            raise errors[failure]
        return {doc_id: GptVote(anchor=True, situation=True, sem=dict.fromkeys(rule.SEM, 1))}, []
    monkeypatch.setattr(monitor, '_claim', claim)
    monkeypatch.setattr(monitor, 'JevClient', Judge)
    monkeypatch.setattr(monitor.gpt, 'judge_batch', gpt)
    register(sid, 'monitor', 'monitor')
    worker.execute(worker.Context(sid, 'v1', 'monitor', {}, 'monitor'))
    work = next(r for r in runner.status(sid) if r['runId'] == 'monitor')
    assert work['state'] == 'done'
    result = store.load_session(sid)['training']['monitor']
    assert result['incomplete'] == 1 and result['n'] == 2
    assert result['errors'][0]['doc_id'] == 'd0' and result['errors'][0]['reason']
    assert result['reason'] and work['detail']['reason']
    assert 'secret provider detail' not in json.dumps(result)
    for cache in monitor.caches_for(sid, store.load_session(sid)).values():
        with cache._db() as db:
            assert not db.execute('SELECT 1 FROM votes WHERE run_id IS NOT NULL').fetchone()
    assert client.post(f'/train/{sid}/export', json={}).status_code == 200


def test_r108_failed_monitor_is_separate_from_readiness(client, data_dir):
    sid, _ = prepared(data_dir)
    register(sid, 'monitor', 'monitor', 'failed')
    store.update_session(sid, {'training': {'monitorRunId': 'monitor'}})
    response = client.get(f'/train/{sid}/status').json()
    assert response['workers'] == []
    assert response['monitor']['state'] == 'failed'
    assert response['monitor']['reason']


@pytest.mark.parametrize('action,state', [('pause','running'), ('stop','running'), ('resume','paused'), ('resume','failed'), ('resume','interrupted')])
def test_r109_infer_controls_and_idempotent_restart(client, data_dir, monkeypatch, action, state):
    sid, _ = prepared(data_dir)
    register(sid, 'old', 'infer', state)
    store.update_session(sid, {'labeling': {'mode': 'model', 'started': True, 'modelId': 'm1', 'inferRunId': 'old'},
                               'training': {'inferRunId': 'old'}})
    launched = []
    def start(s, version, kind, args):
        launched.append((kind, args))
        register(s, 'new', kind)
        return next(r for r in runner.status(s) if r['runId'] == 'new')
    monkeypatch.setattr(runner, 'start', start)
    response = client.post(f'/label/{sid}/judge/infer/{action}')
    assert response.status_code == 200, response.text
    if state in ('failed', 'interrupted'):
        assert launched == [('infer', {'modelId': 'm1'})]
        assert store.load_session(sid)['labeling']['inferRunId'] == 'new'
        assert store.load_session(sid)['training']['inferRunId'] == 'new'
        assert client.post(f'/label/{sid}/judge/infer/resume').status_code == 200
        assert len(launched) == 1
    else:
        with transaction(sid) as db:
            assert db.execute("SELECT action FROM runs WHERE run_id='old'").fetchone()[0] == action


@pytest.mark.parametrize('claim', ['judge', 'monitor'])
@pytest.mark.parametrize('cause', ['inactive', 'missing', 'expired'])
def test_r110_reclaims_alive_pid_leases(data_dir, claim, cause):
    from app.label.judge import cache_root
    from app.model.monitor import _claim
    cache = VoteCache(cache_root('s1', 'p_123456789abc', 'jev', 'context'))
    register('s1', 'old', 'judge')
    cache.seed(['a'])
    assert cache.lease(1, 'old') == ['a']
    with transaction('s1') as db:
        if cause == 'inactive':
            db.execute("UPDATE runs SET state='interrupted' WHERE run_id='old'")
        elif cause == 'missing':
            db.execute("DELETE FROM runs WHERE run_id='old'")
    if cause == 'expired':
        with cache._db() as db:
            db.execute('UPDATE votes SET at=?', (time.time() - 601,))
    other = VoteCache(cache.path.parent)
    assert (other.lease(1, 'new') if claim == 'judge' else _claim(other, 'a', 'new')) == (['a'] if claim == 'judge' else None)
    cache.put('a', {'stale': True})
    assert other.counts()['done'] == 0


def test_r110_judge_wait_is_bounded(setup_judge, monkeypatch):
    env = setup_judge
    env.prepare(1)
    cache = cache_for(env)
    cache.seed(['d000'])
    register('session', 'owner', 'judge')
    cache.lease(1, 'owner')
    ticks = [0]
    monkeypatch.setattr(env.judge, 'LEASE_WAIT_LIMIT', 3, raising=False)
    def sleep(_):
        ticks[0] += 1
        assert ticks[0] <= 3, 'judge waits forever on a live lease'
    monkeypatch.setattr(env.judge.time, 'sleep', sleep)
    register('session', 'run', 'judge')
    ctx = Context()
    env.judge.run_worker(ctx)
    assert next(r for r in runner.status('session') if r['runId'] == 'run')['state'] == 'interrupted'
    assert ctx.details[-1].get('reason')
    assert cache.counts()['pending'] == 1


@pytest.mark.parametrize('exception', [SystemExit, KeyboardInterrupt])
def test_minor6_base_exception_is_interrupted_and_reraised(data_dir, monkeypatch, exception):
    register('s1', 'run', 'test')
    def fail(ctx):
        raise exception()
    monkeypatch.setitem(worker.KINDS, 'test', fail)
    with pytest.raises(exception):
        worker.execute(worker.Context('s1', 'v1', 'test', {}, 'run'))
    assert runner.status('s1')[0]['state'] == 'interrupted'
    assert runner.status('s1')[0]['error'] == exception.__name__


def test_minor7_single_final_materializer():
    from app.label import merge, route
    assert not hasattr(merge, 'rebuild_final')
    assert callable(route.rebuild_final)


@pytest.mark.parametrize('entry', ['train_member', 'train_ensemble'])
def test_minor8_configurable_head_minimum(monkeypatch, entry):
    from app.model import train
    torch.set_num_threads(2)
    monkeypatch.setattr(settings, 'head_min_samples', 1000)
    targets = train.build_targets([row(i) for i in range(40)], {})
    x = np.ones((40, 1032), dtype=np.float32)
    if entry == 'train_member':
        result = train.train_member(x, targets, max_epochs=1)
        assert not result['heads.anchor.weight'].any()
    else:
        result = train.train_ensemble(x, targets, max_epochs=1)
        assert not result.perHead['anchor']['trained']


def test_minor9_known_reads_past_version(client, monkeypatch):
    monkeypatch.setattr(settings, 'embed_backend', 'fake')
    sid = client.post('/context', json={**CTX, 'knownInsights': ['past']}).json()['sid']
    versions.create_version(sid, 'v1', 'stage3', '')
    assert client.put(f'/context/{sid}', json={**CTX, 'knownInsights': ['current']}).status_code == 200
    before = (versions.version_dir(sid, 'v1') / 'session.json').read_bytes()
    assert [i['text'] for i in client.get(f'/known/{sid}?version=v1').json()['items']] == ['past']
    assert (versions.version_dir(sid, 'v1') / 'session.json').read_bytes() == before
    assert client.get(f'/known/{sid}?version=v999').status_code == 404


def test_minor10_stale_prep_wins_over_completed_run(client):
    sid = create(client)
    register(sid, 'prep', 'prep', 'done')
    store.update_session(sid, {'prep': {'status': 'stale', 'runId': 'prep'}})
    assert client.get(f'/prep/{sid}/status').json()['status'] == 'stale'
    assert store.load_session(sid)['prep']['status'] == 'stale'


def test_minor11_human_clears_automatic_mismatch(data_dir):
    from app.label.store import LabelStore
    from app.label.route import submit_item
    labels = LabelStore(data_dir)
    tags = json.loads(row()['tags_json'])
    with labels._db() as db:
        db.execute('INSERT INTO final VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   ('a', 'core', .2, 'agreed', 'escalated:grade_mismatch', json.dumps(tags), None, None, 'r1', 'q1', '{}', '[]', 1))
        db.execute("INSERT INTO queue VALUES ('a','grade_mismatch',1,'open')")
    submit_item(labels, 'a', 'person', 'escalate', tags)
    with labels._db() as db:
        final = db.execute("SELECT * FROM final WHERE doc_id='a'").fetchone()
        assert final['source'] == 'human' and final['confidence'] == 1
        assert final['grade_mismatch'] == 0


@pytest.mark.parametrize('state', ['running', 'paused'])
def test_r110_preserves_fresh_active_run_leases(data_dir, state):
    from app.label.judge import cache_root
    from app.model.monitor import _claim
    cache = VoteCache(cache_root('s1', 'p_123456789abc', 'jev', 'context'))
    register('s1', 'owner', 'judge', state)
    cache.seed(['a'])
    assert cache.lease(1, 'owner') == ['a']
    other = VoteCache(cache.path.parent)
    assert other.lease(1, 'new') == []
    with pytest.raises(store.StoreError):
        _claim(other, 'a', 'new')
    cache.put('a', {'valid': True})
    assert other.counts()['done'] == 1
