"""Offline HTTP journey with real pipelines, schemas, storage and revisions."""
from collections import Counter
import json
from pathlib import Path
import runpy
import socket
import sys
from types import SimpleNamespace

import pytest

from app.context import store as sessions
from app.context.versions import version_dir
from app.config import settings
from app.llm import registry
from app.llm.fake import FakeBackend
from app.persona.store import PersonaStore
from app.work import runner, worker
from tests.fixtures.evidence_package import write_session_with_package, fake_persona_backend


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def offline(monkeypatch, no_external_connections):
    attempts = []
    guarded = socket.socket.connect

    def connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            attempts.append(address)
            pytest.fail(f'Internet socket attempted: {address!r}')
        return guarded(sock, address)

    monkeypatch.setattr(socket.socket, 'connect', connect)
    monkeypatch.setattr(socket.socket, 'connect_ex', connect)
    monkeypatch.setattr(settings, 'embed_backend', 'fake')
    monkeypatch.setattr(settings, 'embed_dim', 1024)
    return attempts


def test_package_to_insights_offline(client, data_dir, monkeypatch, offline):
    synth = write_session_with_package(data_dir)
    sid, version = synth.sid, synth.version
    root = version_dir(sid, version)
    package = sessions.read_json(root / 'evidence/package.json')
    fake = fake_persona_backend(package)
    calls, launches = [], []

    class Backend:
        def run(self, task):
            calls.append(task.task.split('.')[-1])
            if task.task == 'insight.edit':
                output = json.loads(fake.responses['insight.derive'])
                output['items'][0]['title'] = '채팅으로 수정한 제목'
                return FakeBackend(responses={task.task: json.dumps(output)}).run(task)
            return fake.run(task)

    monkeypatch.setattr(registry, 'get_backend', lambda name: Backend())

    def start(sid, version, kind, args):
        # Replace process launch only; dispatch through the real worker registry.
        run_id = f'offline-{len(launches) + 1}'
        launches.append((kind, args))
        worker.KINDS[kind](SimpleNamespace(sid=sid, version=version, args=args,
            run_id=run_id, should_stop=lambda: False, heartbeat=lambda *a: None))
        return {'runId': run_id}

    monkeypatch.setattr(runner, 'start', start)
    persona, insight = f'/persona/{sid}', f'/insight/{sid}'

    def completion():
        return ok(client.get(f'/session/{sid}'))['data']['completion']

    assert not completion()['personaDone']
    assert not completion()['insightDone']
    assert ok(client.post(persona + '/run', json={})) == {'runId': 'offline-1'}
    status = ok(client.get(persona + '/status'))
    assert status['status'] == 'done' and status['progress'] == 1
    assert all(row['status'] == 'done' for row in status['personas'])
    cards = ok(client.get(persona + '/cards'))
    assert len(cards['personas']) == 4 and cards['package_run'] == package['run']
    for block in package['personas']:
        p = block['persona_evidence']
        card = ok(client.get(persona + '/cards/' + p['persona_id']))
        assert card == cards['personas'][p['persona_id']]
        assert {'grades', 'trace', 'prescription', 'scope'} <= card.keys()
    points = ok(client.get(persona + '/map'))['points']
    assert len(points) == 11 and {p['zone'] for p in points} == set('ABCDEF')
    store = PersonaStore.open(sid, version)
    assert ok(client.get(persona + '/tree')) == store.read('tree')
    assert completion()['personaDone'] and not completion()['insightDone']

    assert ok(client.post(insight + '/run', json={'mode': 'derive'})) == {'runId': 'offline-2'}
    original = ok(client.get(insight))
    assert original['insights']['revision'] == 1
    assert len(original['insights']['items']) == 3
    assert original['bars']['bars'] and len(original['radar']) == 3
    assert completion()['insightDone']
    assert store.read('stage_8')['insights'] == 3
    target = original['insights']['items'][0]['id']
    assert ok(client.post(insight + '/concept/' + target)) == {'runId': 'offline-3'}
    concepts = ok(client.get(insight))['concepts']
    assert concepts['revision'] == 1 and len(concepts['items']) == 1
    assert concepts['items'][0]['id'] == target
    assert store.read('stage_8')['concepts'] == 1
    assert ok(client.post(insight + '/chat', json={'target': 'insights', 'message': '제목을 수정해 주세요'})) == {'ok': True, 'revision': 2}
    edited = ok(client.get(insight))['insights']
    assert edited['items'][0]['title'] == '채팅으로 수정한 제목'
    assert edited['items'] != original['insights']['items']
    assert store.read('stage_8')['chat_revisions'] == 1
    assert ok(client.post(insight + '/revert', json={'target': 'insights', 'revision': 1})) == {'revision': 3}
    final = ok(client.get(insight))
    assert final['insights']['items'] == original['insights']['items']
    history = final['insights']['history']
    assert [h['revision'] for h in history] == [1, 2, 3]
    assert [h['by'] for h in history] == ['generate', 'chat', 'revert']
    assert history[0]['items'] == history[2]['items'] == original['insights']['items']
    assert history[1]['items'] == edited['items']
    assert final['concepts']['history'] == concepts['history']
    assert final['concepts']['items'][0]['outdated'] is True
    assert final['bars'] == original['bars'] and final['radar'] == original['radar']
    chat = [json.loads(line) for line in (root / 'persona/chat.jsonl').read_text().splitlines()]
    assert len(chat) == 1 and chat[0]['ok'] and chat[0]['revision'] == 2
    data = ok(client.get(f'/session/{sid}'))['data']
    assert data['completion']['personaDone'] and data['completion']['insightDone']
    assert data['insight']['revision'] == 3 and data['insight']['status'] == 'done'
    report = store.read('stage_8')
    assert ok(client.get(persona + '/status'))['stage8'] == report
    assert {'cards', 'failed', 'grades', 'null_attributes', 'constraint_violations',
            'represcribed', 'blocked', 'future', 'zones', 'stars', 'insights',
            'above_mean', 'concepts', 'chat_revisions', 'llm_calls', 'params',
            'provisional', 'run', 'at'} <= report.keys()
    assert report['cards'] == 4 and report['failed'] == 0
    assert set(report['grades']) == {'observed', 'inferred', 'speculated'}
    assert report['null_attributes'] > 0
    rows = list(cards['personas'].values())
    assert report['constraint_violations'] == sum(
        c['verdict'] == 'violates' for row in rows for c in row['constraint'])
    assert report['represcribed'] == sum(row['prescription']['represcribed'] for row in rows)
    assert report['blocked'] == sum(row['prescription']['blocked'] for row in rows)
    assert report['future'] == sum(row['scope']['verdict'] == 'outside' for row in rows)
    assert report['run'] == cards['run'] and report['at']
    assert report['zones'] == dict(Counter(p['zone'] for p in points))
    assert report['stars'] == 2
    assert (report['insights'], report['concepts'], report['chat_revisions']) == (3, 1, 1)
    assert report['above_mean'] == len(final['bars']['targets'])
    assert report['llm_calls'] == dict(Counter(calls))
    assert report['params']['TRACE_MIN'] == .5 and 'TRACE_MIN' in report['provisional']
    assert [kind for kind, _ in launches] == ['persona', 'insight', 'insight']
    assert offline == []


def test_qa_script_session_is_served(client, data_dir, monkeypatch, capsys, offline):
    script = Path(__file__).resolve().parents[1] / 'scripts/make_persona_qa.py'
    monkeypatch.setattr(sys, 'argv', [str(script), str(data_dir), '--seed', '17', '--big-persona'])
    # Execute the CLI entry point in-process so the socket guard covers it too.
    monkeypatch.setenv('EMBED_BACKEND', 'fake')
    monkeypatch.setenv('LLM_BACKEND', 'fake')
    runpy.run_path(str(script), run_name='__main__')
    output = json.loads(capsys.readouterr().out)
    data = ok(client.get('/session/' + output['sid']))['data']
    assert data['version'] == output['version'] == 'v1'
    assert data['segment']['status'] == data['evidence']['status'] == 'done'
    assert data['completion']['segmentDone']
    assert ok(client.get('/persona/' + output['sid'] + '/status'))['status'] == 'none'
    package = json.loads(Path(output['package']).read_text())
    assert package['params']['seed'] == 17
    assert len(package['personas'][0]['context_evidence']) == 10
    from app.persona.insights import _centroids
    ids = {c['context_id'] for b in package['personas'] for c in b['context_evidence']}
    vectors = _centroids(output['sid'], output['version'], ids)
    assert set(vectors) == ids and all(v.shape == (1024,) for v in vectors.values())
    assert offline == []
