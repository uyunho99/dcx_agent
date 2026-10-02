"""Pending locked rounds must not leak through feedback or manual provenance."""
import pytest

from app.config import settings
from app.context import store
from app.keywords import rounds
from app.keywords.events import KeywordEvent, append_event, load_events
from app.keywords.feedback import write_feedback_md
from test_rounds_api import backend, client, data_dir
from test_round_lock import finish_r1


def seed_feedback(*, committed=False, top_level=False):
    keyword = {'id': 'k_r2g1_0001', 'kw': '숨은후보', 'axis': 'physical',
               'sub': 'space', 'round': 2, 'origin': 'llm', 'status': 'pending'}
    patch = {'keywordRounds': {'2': {'round': 2, 'gen': 1,
        'job': {'status': 'done', 'gen': 1}, 'committed': committed,
        'keywords': [keyword]}}}
    if committed or top_level:
        patch['keywords'] = store.load_session('test')['keywords'] + [keyword]
    store.update_session('test', patch)
    for event in [
        {'type': 'reject', 'kwId': keyword['id'], 'kw': keyword['kw']},
        {'type': 'move', 'kwId': keyword['id'], 'kw': keyword['kw'],
         'to': {'axis': 'physical', 'sub': 'sense'}},
        {'type': 'direction', 'text': '방향X'},
        {'type': 'add', 'kwId': 'manual-old', 'kw': '수동추가'},
    ]:
        append_event('test', KeywordEvent(ts=store.now(), round=2, **event))


@pytest.mark.parametrize('surface', ['write', 'r3_inputs', 'preview'])
def test_pending_locked_feedback_hidden(client, surface):
    finish_r1(client)
    seed_feedback()
    path = store.session_dir('test') / 'keyword_events.jsonl'
    before = path.read_bytes()
    text = write_feedback_md('test')
    if surface == 'r3_inputs':
        text = rounds._inputs('test', store.load_session('test'), 3).feedback_md
    elif surface == 'preview':
        response = client.get('/keywords/test')
        assert response.status_code == 200
        text = response.json()['feedback_md']
    assert '숨은후보' not in text
    assert '방향X' in text
    assert '수동추가' in text
    assert path.read_bytes() == before


@pytest.mark.parametrize('retained_by', ['committed', 'unlocked', 'top_level'])
def test_valid_feedback_retained(client, monkeypatch, retained_by):
    finish_r1(client)
    seed_feedback(committed=retained_by == 'committed', top_level=retained_by == 'top_level')
    if retained_by == 'unlocked':
        monkeypatch.setattr(settings, 'keyword_locked_rounds', [])
    text = write_feedback_md('test')
    assert '숨은후보' in text
    assert '방향X' in text
    assert '수동추가' in text


@pytest.mark.parametrize('event_type', ['approve', 'unreject'])
def test_hidden_restoration_does_not_cancel_visible_rejection(client, event_type):
    finish_r1(client)
    keyword = store.load_session('test')['keywords'][0]
    append_event('test', KeywordEvent(ts=store.now(), round=1, type='reject',
                                    kwId=keyword['id'], kw=keyword['kw']))
    seed_feedback()
    # Same spelling, different ID: a hidden candidate cannot restore a visible keyword.
    append_event('test', KeywordEvent(ts=store.now(), round=2, type=event_type,
                                    kwId='k_r2g1_0001', kw=keyword['kw']))
    assert keyword['kw'] in write_feedback_md('test')


@pytest.mark.parametrize('state,expected', [('pending', 1), ('committed', 2), ('unlocked', 2), ('empty', 1)])
def test_manual_round_ignores_pending_locked_round(client, monkeypatch, state, expected):
    if state != 'empty':
        finish_r1(client)
        seed_feedback(committed=state == 'committed')
    if state == 'unlocked':
        monkeypatch.setattr(settings, 'keyword_locked_rounds', [])
    response = client.post('/keywords/test/manual', json={
        'kw': '저소음', 'axis': 'physical', 'sub': 'sense'})
    assert response.status_code == 200, response.text
    keyword = next(k for k in store.load_session('test')['keywords']
                   if k['id'] == response.json()['id'])
    assert keyword['round'] == expected
    event = load_events('test')[-1]
    assert event.type == 'add' and event.kwId == keyword['id']
    assert event.round == expected
