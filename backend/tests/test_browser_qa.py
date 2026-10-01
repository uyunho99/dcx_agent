"""R-112 browser QA regressions for backend response contracts."""
import importlib
from unittest.mock import Mock

import pytest

from app.known.filter import SearchResult

FALLBACK = '답변 모델이 연결되지 않아 근거 원문만 보여 줍니다.'


@pytest.mark.parametrize('path', ['/chat', '/insight-chat'])
@pytest.mark.parametrize('answer', [None, ''])
@pytest.mark.parametrize('reason', [None, 'all_known'])
def test_q2_unconnected_answer_preserves_search(client, monkeypatch, path, answer, reason):
    chat = importlib.import_module('app.routers.chat')
    sources = [] if reason else [dict(doc_id='d1', title='근거', desc='원문', url='https://example.test/1')]
    monkeypatch.setattr(chat, 'search_docs', Mock(return_value=SearchResult([sources], reason)))
    monkeypatch.setattr(chat, 'call_claude', Mock(return_value=answer))
    monkeypatch.setattr(chat, 'list_objects', lambda *a: [])
    monkeypatch.setattr(chat, 'load_data', lambda *a: [])
    result = client.post(path, json={'sid': 's1', 'query': '질문'}).json()
    assert result['status'] == 'ok'
    assert result['answer'] == FALLBACK
    assert result['sources'] == sources
    assert result['reason'] == reason
    assert result.get('modified', False) is False


@pytest.mark.parametrize('path', ['/chat', '/insight-chat'])
def test_q2_no_sid_keeps_legacy_error_status(client, monkeypatch, path):
    chat = importlib.import_module('app.routers.chat')
    monkeypatch.setattr(chat, 'call_claude', lambda *a, **kw: None)
    result = client.post(path, json={'query': '질문'}).json()
    assert result['status'] == 'error'
    assert result['answer'] == FALLBACK
    assert result['sources'] == []
