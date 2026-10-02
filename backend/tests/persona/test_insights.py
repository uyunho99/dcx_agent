import json
import sqlite3

import numpy as np
import pytest

from app.context import store as sessions
from app.context.versions import version_dir
from app.llm import registry
from app.llm.fake import FakeBackend
from app.persona.insights import InsightError, confirm, derive, opportunity_bars
from app.persona.package import load_package
from app.persona.store import PersonaStore
from tests.fixtures.evidence_package import write_session_with_package, fake_persona_backend


class Embedder:
    def embed(self, texts, input_type=None):
        assert input_type == 'query'
        return np.eye(3)


@pytest.fixture
def env(data_dir):
    session = write_session_with_package(data_dir)
    store = PersonaStore.open(session.sid, session.version)
    cards = {'items': [{'persona_id': 'CL0-P0', 'summary': {'intent': {'text': 'カード要約'}}}]}
    store.write('cards', cards)
    package = load_package(session.sid, session.version)
    with sqlite3.connect(version_dir(session.sid, session.version) / 'segment/segment.sqlite') as db:
        for n, context in enumerate(c for b in package.personas for c in b.context_evidence):
            db.execute('UPDATE contexts SET centroid=? WHERE context_id=?',
                       (np.eye(3, dtype=np.float32)[n % 3].tobytes(), context.context_id))
    backend = fake_persona_backend(package)
    rows = json.loads(backend.responses['insight.derive'])['items']
    return session, store, rows, cards


def runner(monkeypatch, responses):
    pending = iter(responses)
    calls = []
    class Backend:
        def run(self, task):
            calls.append(task)
            return FakeBackend(responses={task.task: json.dumps({'items': next(pending)})}).run(task)
    monkeypatch.setattr(registry, 'get_backend', lambda name: Backend())
    return calls


@pytest.mark.parametrize('count', [0, 2, 9])
def test_range_regenerates_once_then_fails(env, monkeypatch, count):
    session, store, rows, _ = env
    invalid = [{**rows[n % 3], 'id': f'I{n}'} for n in range(count)]
    calls = runner(monkeypatch, [invalid, invalid])
    with pytest.raises(InsightError, match='^인사이트를 만들지 못했습니다. 다시 시도하세요.$'):
        derive(session.sid, session.version, embedder=Embedder())
    assert len(calls) == 2
    assert store.read('insights') is None


@pytest.mark.parametrize('count', [3, 8])
def test_range_recovery_revision_and_cards_input(env, monkeypatch, count):
    session, store, rows, cards = env
    valid = [{**rows[n % 3], 'id': f'I{n}'} for n in range(count)]
    calls = runner(monkeypatch, [[], valid, valid])
    assert derive(session.sid, session.version, embedder=Embedder()) == 1
    first = store.read('insights')
    assert derive(session.sid, session.version, embedder=Embedder()) == 2
    assert store.read('insights')['history'][0]['items'] == first['items']
    assert json.loads(calls[0].attachments[0].body)['cards'] == cards
    assert calls[0].task == 'insight.derive'


def test_known_badge(env, monkeypatch):
    session, store, rows, _ = env
    rows[0]['known_ki_id'] = 'k1'
    sessions.update_session(session.sid, {'knownInsights': [{'id': 'k1', 'text': '알려진 내용'}]})
    calls = runner(monkeypatch, [rows])
    derive(session.sid, session.version, embedder=Embedder())
    items = store.read('insights')['items']
    assert items[0]['known_badge'] == 'Known Insight #k1와 같은 내용'
    assert items[1]['known_badge'] is None
    assert json.loads(calls[0].attachments[0].body)['known_insights'][0]['id'] == 'k1'


def test_bars_mean_and_targets():
    result = opportunity_bars([{'id': 'a', 'context_ids': ['x', 'y']},
        {'id': 'b', 'context_ids': ['y']}, {'id': 'c', 'context_ids': ['z']}],
        {'x': 0, 'y': 2, 'z': 3})
    assert result == {'bars': [{'id': 'a', 'odi': 1}, {'id': 'b', 'odi': 2},
                               {'id': 'c', 'odi': 3}], 'mean': 2, 'targets': ['b', 'c']}


def test_llm_numbers_ignored(env, monkeypatch):
    session, store, rows, _ = env
    for row in rows:
        row.update(radar={'raw': 999}, odi=999, percentile=999, default_target=True)
    runner(monkeypatch, [rows])
    derive(session.sid, session.version, embedder=Embedder())
    items = store.read('insights')['items']
    assert items[0]['radar']['raw'] == dict(Computed=1, Connected=0, Shared=0)
    assert items[0]['radar']['percentile']['Computed'] == pytest.approx(100 * 2.5 / 3)
    assert [i['odi'] for i in items] == pytest.approx([.05, .75, 1.36])
    assert [i['default_target'] for i in items] == [False, True, True]
    assert 'percentile' not in items[0]


def test_confirm_sets_session(env, monkeypatch):
    session, store, rows, _ = env
    runner(monkeypatch, [rows])
    derive(session.sid, session.version, embedder=Embedder())
    sessions.update_session(session.sid, {'persona': {'status': 'done'}})
    assert confirm(session.sid, session.version, ['I1', 'I3']) == ['I1', 'I3']
    assert sessions.load_session(session.sid)['insight']['confirmed'] == ['I1', 'I3']
    with pytest.raises(sessions.StoreError):
        confirm(session.sid, session.version, ['missing'])
    assert confirm(session.sid, session.version, []) == []


def test_unknown_context_rejected_without_revision(env, monkeypatch):
    session, store, rows, _ = env
    rows[0]['context_ids'] = ['missing']
    runner(monkeypatch, [rows, rows])
    with pytest.raises(InsightError):
        derive(session.sid, session.version, embedder=Embedder())
    assert store.read('insights') is None


def test_derive_weights_context_cosines_by_document_count(env, monkeypatch):
    session, store, rows, _ = env
    path = version_dir(session.sid, session.version) / 'evidence/package.json'
    package = json.loads(path.read_text())
    contexts = package['personas'][0]['context_evidence']
    contexts[0]['metrics']['doc_count'] = 1
    contexts[1]['metrics']['doc_count'] = 3
    path.write_text(json.dumps(package), encoding='utf-8')
    rows[0]['context_ids'] = [contexts[0]['context_id'], contexts[1]['context_id']]
    runner(monkeypatch, [rows])
    derive(session.sid, session.version, embedder=Embedder())
    first = store.read('insights')['items'][0]
    assert first['radar']['raw'] == pytest.approx(dict(Computed=.25, Connected=.75, Shared=0))
    # ODI remains the unweighted mean even though the radar is weighted.
    assert first['odi'] == pytest.approx(.4)


def test_missing_centroid_preserves_previous_revision(env, monkeypatch):
    session, store, rows, _ = env
    runner(monkeypatch, [rows, rows])
    derive(session.sid, session.version, embedder=Embedder())
    previous = store.read('insights')
    with sqlite3.connect(version_dir(session.sid, session.version) / 'segment/segment.sqlite') as db:
        db.execute('UPDATE contexts SET centroid=NULL WHERE context_id=?', (rows[0]['context_ids'][0],))
    with pytest.raises(InsightError):
        derive(session.sid, session.version, embedder=Embedder())
    assert store.read('insights') == previous
