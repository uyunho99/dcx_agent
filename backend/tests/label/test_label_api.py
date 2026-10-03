import importlib
import json
import time
from pathlib import Path

import pytest

from app.context import store, versions
from app.label.store import LabelStore
from app.label import audit, rule, questions
from app.label.schema import Tags


def tags(value=1):
    return Tags(anchor=bool(value), situation=bool(value), sem=dict.fromkeys(rule.SEM, value)).model_dump()


@pytest.fixture
def session(data_dir, monkeypatch):
    monkeypatch.setattr('app.config.settings.jev_backend', 'fake')
    monkeypatch.setattr('app.config.settings.label_fake_jev_cross', True)
    store.update_session('labeltest', {'schemaVersion': 2, 'prep': {'status': 'done',
        'derivedRef': {'collectionId': 'c1', 'prepKey': 'p_123456789abc'}}})
    # Minimal context sufficient for labeling; avoid the unrelated context editor validator.
    data = store.load_session('labeltest')
    data['projectContext'] = {'oneLiner': '테스트 정의'}
    store.write_json(store.session_dir('labeltest') / 'session.json', data)
    root = data_dir / 'derived/labeltest/c1/p_123456789abc/docs'
    root.mkdir(parents=True)
    (root / 'part.jsonl').write_text(json.dumps({'doc_id': 'd', 'text': '원문', 'votes': 'must hide'}))
    return 'labeltest', LabelStore(store.session_dir('labeltest'))


def seed_queue(labels, n=1):
    with labels._db() as db:
        db.executemany("INSERT INTO queue VALUES (?, 'labeler_failed', 0, 'open')",
                       ((f'd{i}' if n > 1 else 'd',) for i in range(n)))


def seed_final(labels, n=1):
    with labels._db() as db:
        db.executemany('INSERT INTO final VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
            ((f'd{i}' if n > 1 else 'd', 'core', .9, 'agreed', 'accepted',
              json.dumps(tags()), None, None, rule.RULE_VERSION, questions.QVER,
              json.dumps({'jev': {'probs': dict.fromkeys(rule.GRADE_FIELDS, 1)}, 'gpt': tags()}), '[]', 0)
             for i in range(n)))


def test_queue_large_next_is_constant_time(client, session):
    sid, labels = session
    seed_queue(labels, 40000)
    client.get('/health')
    start = time.perf_counter()
    response = client.get(f'/label/{sid}/next')
    elapsed = time.perf_counter() - start
    assert response.status_code == 200
    assert response.json()['item']['doc_id'] == 'd0'
    assert elapsed < .05, elapsed


def test_submit_is_durable_per_item(client, session):
    sid, labels = session
    seed_queue(labels)
    response = client.post(f'/label/{sid}/submit', json={'doc_id': 'd', 'labeler': 'alice', 'mode': 'escalate', 'tags': tags()})
    assert response.status_code == 200
    assert LabelStore(labels.path.parent).get('d').source == 'human'
    with labels._db() as db:
        assert db.execute('SELECT count(*) FROM human').fetchone()[0] == 1
    assert client.get(f'/label/{sid}/next').json()['item'] is None


def test_next_hides_votes_until_submit(client, session):
    sid, labels = session
    seed_final(labels)
    seed_queue(labels)
    response = client.get(f'/label/{sid}/next')
    assert response.status_code == 200
    item = response.json()['item']
    assert not {'votes', 'tags', 'level', 'confidence', 'anchor'} & item.keys()
    response = client.post(f'/label/{sid}/submit', json={'doc_id': 'd', 'labeler': 'alice', 'mode': 'escalate', 'tags': tags()})
    assert set(response.json()['votes']) == {'jev', 'gpt'}


def test_legacy_label_reads_as_anchor(client, data_dir):
    store.update_session('oldlabel', {'labeledData': [{'doc_id': 'old', 'label': 1}]})
    response = client.get('/label/oldlabel/overview')
    assert response.status_code == 200
    assert response.json()['legacyLabels'][0]['anchor'] is True
    assert client.post('/label/oldlabel/start').status_code == 409


def test_mode_locked_after_start(client, session, monkeypatch):
    sid, _ = session
    module = importlib.import_module('app.routers.labeling_v2')
    calls = []
    def start(s, v, kind, args):
        calls.append((s, v, kind, args))
        return {'runId': args['labeler'], 'state': 'running', 'progress': 0}
    monkeypatch.setattr(module.runner, 'start', start)
    assert client.post(f'/label/{sid}/mode', json={'mode': 'llm'}).status_code == 200
    assert client.post(f'/label/{sid}/start').status_code == 200
    assert calls == [(sid, 'v1', 'judge', {'labeler': name}) for name in ('jev', 'gpt')]
    response = client.post(f'/label/{sid}/mode', json={'mode': 'llm'})
    assert response.status_code == 409
    assert response.json()['error']['message'] == '새 버전에서 방식을 바꾸세요'


def test_rule_preview(client):
    response = client.post('/label/rule/preview', json={'tags': tags()})
    assert response.status_code == 200
    assert response.json() == {'level': 'core'}


def test_audit_submit_overrides_and_round_is_required(client, session):
    sid, labels = session
    seed_final(labels)
    audit.maybe_new_round(labels, 1000)
    item = client.get(f'/label/{sid}/next?mode=audit').json()['item']
    assert item['round'] == 1
    body = {'doc_id': item['doc_id'], 'labeler': 'alice', 'mode': 'audit', 'tags': tags(0)}
    assert client.post(f'/label/{sid}/submit', json=body).status_code == 409
    body['round'] = item['round']
    assert client.post(f'/label/{sid}/submit', json=body).status_code == 200
    assert labels.get('d').source == 'human'
    assert labels.get('d').evidence_level == 'non'
    assert client.get(f'/label/{sid}/next?mode=audit').json()['item'] is None


def test_overview_and_report(client, session):
    sid, labels = session
    seed_final(labels)
    response = client.get(f'/label/{sid}/overview')
    assert response.status_code == 200
    view = response.json()
    assert view['now']['state'] == 'before_start'
    for name in ('mismatchRate', 'labelerAccuracy', 'selfConsistency', 'definitionCheck',
                 'progress', 'levelDistribution', 'queue', 'changes', 'audit'):
        assert name in view
    assert view['changes']['accepted'] == 1
    assert client.get(f'/label/{sid}/overview').json()['changes']['accepted'] == 1
    assert client.post(f'/label/{sid}/seen').status_code == 200
    assert client.get(f'/label/{sid}/overview').json()['changes']['accepted'] == 1
    assert client.post(f'/label/{sid}/seen').status_code == 200
    assert client.get(f'/label/{sid}/overview').json()['changes']['accepted'] == 0
    report = importlib.import_module('app.label.report').label_part(sid)
    assert report['accepted'] == 1
    assert not (labels.path.parent / 'stage_5.json').exists()


def test_version_and_validation_guards(client, session):
    sid, labels = session
    assert client.get(f'/label/{sid}/next?mode=wrong').status_code == 422
    assert client.post(f'/label/{sid}/submit', json={'doc_id': 'missing', 'labeler': 'alice', 'mode': 'escalate', 'tags': tags()}).status_code == 409
    assert client.post(f'/label/{sid}/mode?version=v2', json={'mode': 'llm'}).status_code == 409
    assert client.post(f'/label/{sid}/alpha', json={}).status_code == 404


@pytest.mark.parametrize('started,state,definition,queue,pending,expected', [
    (False, 'paused', True, 1, True, 'before_start'),
    (True, 'paused', True, 1, True, 'paused'),
    (True, 'running', True, 1, True, 'definition_check'),
    (True, 'running', False, 1, True, 'review'),
    (True, 'running', False, 0, True, 'audit'),
    (True, 'running', False, 0, False, 'running'),
    (True, 'done', False, 0, False, 'done'),
])
def test_now_card_priority(started, state, definition, queue, pending, expected):
    from app.label.overview import now_card
    result = now_card(started, {'jev': {'state': state, 'pending': 0}},
                      {'needed': definition, 'reason': '점검'}, queue, pending)
    assert result['state'] == expected


def test_original_body_is_available_without_ai_fields(client, session, data_dir):
    sid, labels = session
    path = data_dir / 'derived/labeltest/c1/p_123456789abc/docs/part.jsonl'
    path.write_text(json.dumps({'doc_id': 'd', 'body': '본문입니다', 'comments': [{'text': '댓글', 'votes': 'hidden'}], 'votes': 'hidden'}))
    client.get(f'/label/{sid}/overview')
    seed_queue(labels)
    doc = client.get(f'/label/{sid}/next').json()['item']['document']
    assert doc['body'] == '본문입니다'
    assert doc['comments'] == [{'text': '댓글'}]
    assert 'votes' not in doc


def test_manual_audit_and_reissue_rounds(client, session, monkeypatch):
    sid, labels = session
    seed_final(labels, 4)
    monkeypatch.setattr('app.config.settings.audit_size', 2)
    assert client.post(f'/label/{sid}/audit').json()['round'] == 1
    assert client.post(f'/label/{sid}/audit').status_code == 409
    for _ in range(2):
        item = client.get(f'/label/{sid}/next?mode=audit').json()['item']
        body = dict(doc_id=item['doc_id'], mode='audit', labeler='alice', round=item['round'], tags=tags())
        assert client.post(f'/label/{sid}/submit', json=body).status_code == 200
    assert client.post(f'/label/{sid}/audit').json()['round'] == 2
    for _ in range(2):
        item = client.get(f'/label/{sid}/next?mode=reissue').json()['item']
        assert item['round'] == 2
        assert 'votes' not in item
        body = dict(doc_id=item['doc_id'], mode='reissue', labeler='alice', round=2, tags=tags())
        assert client.post(f'/label/{sid}/submit', json=body).status_code == 200
        assert client.post(f'/label/{sid}/submit', json=body).status_code == 409
    assert audit.self_consistency(labels)['n'] == 2
    assert client.get(f'/label/{sid}/next?mode=reissue').json()['item'] is None


def test_failed_cache_visible_through_overview(client, session):
    from app.label.overview import caches_for
    sid, labels = session
    caches = caches_for(sid, store.load_session(sid))
    for cache in caches.values():
        cache.seed(['d'])
    for _ in range(3):
        caches['jev'].fail('d', 'invalid')
    result = client.get(f'/label/{sid}/overview').json()
    assert result['queue']['byReason']['labeler_failed'] == 1
    assert result['progress']['jev']['bad'] == 1
    assert client.get(f'/label/{sid}/next').json()['item']['doc_id'] == 'd'


def test_historical_overview_does_not_merge_new_votes(client, session, monkeypatch):
    sid, labels = session
    from app.label import overview as module
    # Copying a version is covered by context tests; provide the archived snapshot here.
    data = store.load_session(sid)
    store.write_json(versions.version_dir(sid, 'v2') / 'session.json', {**data, 'version': 'v2'})
    def forbidden(*args, **kwargs):
        pytest.fail('Historical overview must not refresh immutable results')
    monkeypatch.setattr(module, 'rebuild_queue', forbidden)
    response = client.get(f'/label/{sid}/overview?version=v2')
    assert response.status_code == 200


def test_controls_resume_interrupted_worker(client, session, monkeypatch):
    from app.routers import labeling_v2 as module
    sid, labels = session
    store.update_session(sid, {'labeling': {'started': True, 'judgeRuns': {'jev': 'old'}}})
    monkeypatch.setattr(module.runner, 'status', lambda _: [{'runId': 'old', 'state': 'interrupted'}])
    calls = []
    def start(*args):
        calls.append(args)
        return {'runId': 'new', 'state': 'running'}
    monkeypatch.setattr(module.runner, 'start', start)
    assert client.post(f'/label/{sid}/judge/jev/resume').json()['runId'] == 'new'
    assert calls == [(sid, 'v1', 'judge', {'labeler': 'jev'})]
    assert store.load_session(sid)['labeling']['judgeRuns']['jev'] == 'new'


def test_submit_rolls_back_projection_failure(client, session):
    sid, labels = session
    seed_queue(labels)
    with labels._db() as db:
        db.execute("CREATE TRIGGER reject_final BEFORE INSERT ON final BEGIN SELECT RAISE(ABORT, 'disk fixture'); END")
    response = client.post(f'/label/{sid}/submit', json=dict(doc_id='d', labeler='alice', mode='escalate', tags=tags()))
    assert response.status_code == 500
    assert response.json()['error']['kind'] == 'storage'
    with labels._db() as db:
        assert db.execute('SELECT count(*) FROM human').fetchone()[0] == 0
        assert db.execute('SELECT status FROM queue').fetchone()[0] == 'open'


def test_report_labeler_kappa_is_pairwise_not_human_accuracy(client, session):
    sid, labels = session
    seed_final(labels, 2)
    zero_votes = {'jev': {'probs': dict.fromkeys(rule.GRADE_FIELDS, 0)}, 'gpt': tags(0)}
    with labels._db() as db:
        db.execute('UPDATE final SET votes_json=? WHERE doc_id=?', (json.dumps(zero_votes), 'd0'))
    report = importlib.import_module('app.label.report').label_part(sid)
    assert report['kappaLabelers'] == dict.fromkeys(rule.GRADE_FIELDS, 1.0)
    assert report['agreementRate'] == 1
    assert report['labelerAccuracy']['n'] == 0


def test_failed_submit_returns_surviving_vote_after_commit(client, session):
    from app.label.overview import caches_for
    sid, labels = session
    caches = caches_for(sid, store.load_session(sid))
    for cache in caches.values():
        cache.seed(['d'])
    caches['jev'].mark_bad('d', 'invalid')
    caches['gpt'].put('d', tags())
    client.get(f'/label/{sid}/overview')
    response = client.post(f'/label/{sid}/submit', json=dict(doc_id='d', labeler='alice', mode='escalate', tags=tags(0)))
    assert response.status_code == 200
    assert response.json()['votes']['gpt'] == tags()
    assert labels.get('d').votes['gpt'] == tags()
    assert labels.get('d').source == 'human'


def test_overview_reads_preserve_seen_and_estimates(client, session, monkeypatch):
    from app.label import overview as module
    sid, labels = session
    seed_final(labels)
    store.update_session(sid, {'labeling': {'lastSeenAt': '2000-01-01T00:00:00+00:00'}})
    calls = []
    monkeypatch.setattr(module.judge, 'estimate', lambda *a, **k: calls.append(a[2]) or {'seconds': 0, 'jevTokens': 0})
    first = client.get(f'/label/{sid}/overview').json()
    second = client.get(f'/label/{sid}/overview').json()
    assert first['changes'] == second['changes']
    assert store.load_session(sid)['labeling']['lastSeenAt'] == first['lastSeenAt']
    assert calls == ['jev', 'gpt']
    assert client.post(f'/label/{sid}/seen').status_code == 200
    assert client.get(f'/label/{sid}/overview').json()['changes']['accepted'] == 1
    assert client.post(f'/label/{sid}/seen').status_code == 200
    assert client.get(f'/label/{sid}/overview').json()['changes']['accepted'] == 0
    assert client.post(f'/label/{sid}/seen?version=v99').status_code == 409


def test_next_syncs_empty_queue_without_overview(client, session):
    from app.label.overview import caches_for
    sid, labels = session
    cache = caches_for(sid, store.load_session(sid))['jev']
    cache.seed(['d'])
    cache.mark_bad('d', 'invalid')
    response = client.get(f'/label/{sid}/next')
    assert response.status_code == 200
    assert response.json()['item']['doc_id'] == 'd'


def test_next_skip_keyset(client, session):
    sid, labels = session
    seed_queue(labels, 3)
    first = client.get(f'/label/{sid}/next').json()['item']
    second = client.get(f'/label/{sid}/next', params={'after': '0:d0'}).json()['item']
    assert second['doc_id'] != first['doc_id']
    assert second['cursor'] == '0.0:d1'
    assert client.get(f'/label/{sid}/next', params={'after': '0:d2'}).json()['item'] is None
    for cursor in ('garbage', 'nan:d0', 'inf:d0', '0:'):
        assert client.get(f'/label/{sid}/next', params={'after': cursor}).status_code == 422


def test_overview_and_next_do_not_take_session_lock(client, session, monkeypatch):
    sid, labels = session
    seed_queue(labels, 40000)
    def forbidden(*a, **kw):
        raise AssertionError('Read/sync must not take the session lock')
    monkeypatch.setattr(store, 'locked', forbidden)
    assert client.get(f'/label/{sid}/next').status_code == 200
    assert client.get(f'/label/{sid}/overview').status_code == 200


def test_qa_q11_mismatch_rate_survives_review_and_excludes_failures(client, session):
    sid, labels = session
    seed_final(labels, 4)
    with labels._db() as db:
        db.execute("UPDATE final SET grade_mismatch=1, route='escalated:grade_mismatch' WHERE doc_id IN ('d0','d1')")
        db.execute("INSERT INTO queue VALUES ('failed', 'labeler_failed', 0, 'open')")
    before = client.get(f'/label/{sid}/overview').json()
    assert before['merged'] == 4
    assert before['queue']['total'] == 3
    assert before['mismatchRate'] == .5
    for doc_id in ('d0', 'd1', 'failed'):
        response = client.post(f'/label/{sid}/submit', json={
            'doc_id': doc_id, 'labeler': 'person', 'mode': 'escalate', 'tags': tags()})
        assert response.status_code == 200, response.text
    after = client.get(f'/label/{sid}/overview').json()
    assert after['queue']['total'] == 0
    assert after['merged'] == 4
    assert after['mismatchRate'] == .5
