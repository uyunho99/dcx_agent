"""Version-local persistence, failure atomicity, and append-only revisions."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path

import pytest

from app.context import store as sessions
from app.context.versions import version_dir
from app.persona import params
from app.persona.store import PersonaStore


@pytest.fixture
def store(data_dir):
    sessions.update_session('persona-test', {'sid': 'persona-test', 'schemaVersion': 2})
    return PersonaStore.open('persona-test', 'v1')


def test_params_match_brief():
    expected = dict(CARD_CHUNK=4, TRACE_MIN=0.5,
        OBSERVED_FIELDS=('state', 'barrier', 'usage_context'),
        INFERRED_FIELDS=('emotion', 'jtbd', 'unmet_need'), S_LINE=0.5,
        STAR_NOVELTY=('high', 'very_high'), STAR_MIN=2,
        RADAR_AXES={'Computed': '맞춤형 서비스가 필요해', 'Connected': '실시간으로 직접 보고 싶어', 'Shared': '함께 즐기고 싶어'},
        INSIGHT_RANGE=(3, 8), CX_4D=('정신적', '물리적', '문화적', '시스템'),
        PROVISIONAL=('odi', 'persona_metrics', 'TRACE_MIN', 'RADAR_AXES'))
    assert {key: getattr(params, key) for key in expected} == expected


@pytest.mark.parametrize('name', ['cards', 'map', 'tree', 'insights', 'concepts', 'stage_8'])
def test_read_write_version_local(store, name):
    assert store.read(name) is None
    data = {'text': '냉방 사용', 'nested': {'items': [1, None]}}
    store.write(name, data)
    path = version_dir('persona-test', 'v1') / 'persona' / f'{name}.json'
    assert json.loads(path.read_text(encoding='utf-8')) == data
    assert PersonaStore.open('persona-test', 'v1').read(name) == data
    assert PersonaStore.open('persona-test', 'v2').read(name) is None
    assert PersonaStore.open('another-session', 'v1').read(name) is None


@pytest.mark.parametrize('failure', ['serialize', 'fsync', 'replace'])
def test_atomic_write_failure_keeps_previous_file(store, monkeypatch, failure):
    store.write('cards', {'run': 'old'})
    path = version_dir('persona-test', 'v1') / 'persona' / 'cards.json'
    previous = path.read_bytes()
    data = {'run': object()} if failure == 'serialize' else {'run': 'new'}
    if failure != 'serialize':
        def fail(*args):
            if failure == 'replace':
                temporary = Path(args[0])
                assert json.loads(temporary.read_text()) == data
                assert temporary.parent == path.parent
            raise OSError('injected write failure')
        monkeypatch.setattr(sessions.os, failure, fail)
    with pytest.raises((TypeError, OSError)):
        store.write('cards', data)
    assert path.read_bytes() == previous
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize('name', ['insights', 'concepts'])
def test_new_revision_retains_full_history(store, name):
    first = [{'id': 'I1', 'nested': {'title': '처음'}}]
    assert store.new_revision(name, first, by='generate', message=None) == 1
    snapshot = store.read(name)
    first[0]['nested']['title'] = 'caller mutation'
    second = [{'id': 'I1', 'nested': {'title': '수정'}}]
    assert PersonaStore.open('persona-test', 'v1').new_revision(
        name, second, by='chat', message='제목 수정') == 2
    result = store.read(name)
    assert result['revision'] == 2 and result['items'] == second
    assert result['history'][:1] == snapshot['history']
    assert [h['revision'] for h in result['history']] == [1, 2]
    assert result['history'][0]['items'] == snapshot['items']
    assert [h['by'] for h in result['history']] == ['generate', 'chat']
    assert [h['message'] for h in result['history']] == [None, '제목 수정']
    assert all(datetime.fromisoformat(h['at']).tzinfo for h in result['history'])


def test_revert_appends_new_revision_and_keeps_history(store):
    store.new_revision('insights', [{'title': '처음'}], by='generate', message=None)
    store.new_revision('insights', [{'title': '수정'}], by='chat', message='수정')
    previous = deepcopy(store.read('insights'))
    assert store.revert('insights', 1) == 3
    result = store.read('insights')
    assert result['revision'] == 3
    assert result['items'] == previous['history'][0]['items']
    assert result['history'][:2] == previous['history']
    assert result['history'][-1]['by'] == 'revert'
    assert result['history'][-1]['items'] == result['items']
    assert store.revert('insights', 2) == 4
    assert store.read('insights')['items'] == previous['items']


def test_missing_revision_does_not_mutate(store):
    with pytest.raises(sessions.StoreError) as exc:
        store.revert('insights', 1)
    assert (exc.value.status, exc.value.kind) == (404, 'not_found')
    assert store.read('insights') is None
    store.new_revision('insights', [], by='generate', message=None)
    previous = store.read('insights')
    with pytest.raises(sessions.StoreError):
        store.revert('insights', 42)
    assert store.read('insights') == previous


def test_failed_revision_preserves_history(store, monkeypatch):
    store.new_revision('insights', [], by='generate', message=None)
    previous = store.read('insights')
    def fail(*args):
        raise OSError('replace failed')
    monkeypatch.setattr(sessions.os, 'replace', fail)
    with pytest.raises(OSError):
        store.new_revision('insights', [{'id': 'I1'}], by='chat', message='edit')
    assert store.read('insights') == previous


def test_append_chat_json_lines(store):
    rows = [{'role': 'user', 'message': '수정\n해주세요'},
            {'role': 'assistant', 'ok': True, 'revision': 2}]
    store.append_chat(rows[0])
    path = version_dir('persona-test', 'v1') / 'persona/chat.jsonl'
    previous = path.read_bytes()
    PersonaStore.open('persona-test', 'v1').append_chat(rows[1])
    assert path.read_bytes().startswith(previous)
    assert [json.loads(line) for line in path.read_text().splitlines()] == rows
    assert path.read_bytes().endswith(b'\n')
    with pytest.raises(TypeError):
        store.append_chat({'bad': object()})
    assert [json.loads(line) for line in path.read_text().splitlines()] == rows


@pytest.mark.parametrize('name', ['../session', '/tmp/cards', 'cards.json', 'chat'])
def test_invalid_name_rejected(store, name):
    with pytest.raises(sessions.StoreError) as exc:
        store.write(name, {})
    assert (exc.value.status, exc.value.kind) == (400, 'validation')
