"""Opt-in AC-06 measurement of the real overview endpoint on 310,000 docs."""
import json
import socket
from time import perf_counter

import pytest

from app.context import store, versions
from app.label import overview, questions, route, rule
from app.label.schema import Tags
from app.label.store import LabelStore


DOCUMENT_COUNT = 310_000
QUEUE_COUNT = DOCUMENT_COUNT // 10


@pytest.fixture
def large_session(data_dir, monkeypatch):
    def no_network(*args, **kwargs):
        pytest.fail('The overview performance test must run offline')

    monkeypatch.setattr(socket.socket, 'connect', no_network)
    sid = 'overview-perf'
    store.update_session(sid, {
        'schemaVersion': 2,
        'prep': {'status': 'done', 'derivedRef': {
            'collectionId': 'c1', 'prepKey': 'p_123456789abc'}},
        'labeling': {'started': True},
    })
    data = store.load_session(sid)
    data['projectContext'] = {'oneLiner': 'Synthetic overview performance corpus'}
    store.write_json(store.session_dir(sid) / 'session.json', data)
    labels = LabelStore(versions.version_dir(sid, data['version']))
    route.schema(labels)
    tags = Tags(anchor=True, situation=True, sem=dict.fromkeys(rule.SEM, 1))
    tags_json = tags.model_dump_json()
    votes_json = json.dumps({
        'jev': {'probs': dict.fromkeys(rule.GRADE_FIELDS, 1)},
        'gpt': tags.model_dump(),
    })
    # Bulk setup is outside the timer; normal event triggers remain enabled.
    with labels._db() as db:
        db.executemany('INSERT INTO final VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', (
            (f'd{i:06d}', 'core', .9, 'agreed',
             'escalated:grade_mismatch' if i < QUEUE_COUNT else 'accepted',
             tags_json, None, None, rule.RULE_VERSION, questions.QVER,
             votes_json, '[]', int(i < QUEUE_COUNT))
            for i in range(DOCUMENT_COUNT)
        ))
        db.executemany('INSERT INTO queue VALUES (?, ?, ?, ?)', (
            (f'd{i:06d}', 'grade_mismatch', 1.9, 'open')
            for i in range(QUEUE_COUNT)
        ))
    docs = data_dir / f'derived/{sid}/c1/p_123456789abc/docs'
    docs.mkdir(parents=True)
    with (docs / 'part.jsonl').open('w', encoding='utf-8') as stream:
        for i in range(DOCUMENT_COUNT):
            stream.write(json.dumps({
                'doc_id': f'd{i:06d}', 'text': 'Synthetic document for labeling.',
                'title': f'Document {i}', 'channel': 'blog',
                'url': f'https://example.invalid/doc/{i}',
            }) + '\n')
    overview._estimate.cache_clear()
    try:
        yield sid, labels
    finally:
        overview._estimate.cache_clear()


@pytest.mark.perf
def test_overview_310000_documents(client, large_session):
    sid, labels = large_session
    elapsed = []
    for name in ('cold', 'warm'):
        start = perf_counter()
        response = client.get(f'/label/{sid}/overview')
        elapsed.append(perf_counter() - start)
        print(f'overview documents={DOCUMENT_COUNT} {name}={elapsed[-1]:.6f}s')
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['total'] == DOCUMENT_COUNT
        assert result['accepted'] == DOCUMENT_COUNT - QUEUE_COUNT
        assert result['merged'] == DOCUMENT_COUNT
        assert result['levelDistribution'] == {
            'core': DOCUMENT_COUNT, 'supporting': 0, 'non': 0}
        assert result['queue']['total'] == QUEUE_COUNT
        assert result['queue']['byReason']['grade_mismatch'] == QUEUE_COUNT
    with labels._db() as db:
        assert db.execute('SELECT count(*) FROM documents').fetchone()[0] == DOCUMENT_COUNT
    assert elapsed[1] <= .5, f'Warm overview took {elapsed[1]:.6f}s (target <= 0.5s)'
