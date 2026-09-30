from unittest.mock import Mock
import requests
from app.config import settings
from app.llm.claude_api import ClaudeApiBackend
from app.llm.openai_api import OpenAIApiBackend
from app.llm.compose import CONTEXT_HEADER
from app.services.claude import call_claude


def test_claude_transport_and_legacy_wrapper(task, monkeypatch):
    monkeypatch.setattr(settings, 'claude_api_key', 'x')
    response = Mock(status_code=200)
    response.json.return_value = {'content': [{'text': '{"value":3}'}]}
    post = Mock(return_value=response)
    monkeypatch.setattr('app.llm.claude_api.requests.post', post)
    assert ClaudeApiBackend().run(task).data.value == 3
    assert post.call_args.kwargs['json']['system'].startswith(CONTEXT_HEADER)
    assert task.attachments[0].body in post.call_args.kwargs['json']['system']
    response.json.return_value = {'content': [{'text': 'free text'}]}
    assert call_claude('hello', 42, 'legacy-model', 7) == 'free text'
    kwargs = post.call_args.kwargs
    assert post.call_args.args == ('https://api.anthropic.com/v1/messages',)
    assert kwargs['headers'] == {
        'x-api-key': 'x', 'anthropic-version': '2023-06-01',
        'Content-Type': 'application/json',
    }
    assert kwargs['timeout'] == 7
    assert 'system' not in kwargs['json']
    assert set(kwargs['json']) == {'model', 'max_tokens', 'messages'}
    assert kwargs['json']['model'] == 'legacy-model'
    assert kwargs['json']['max_tokens'] == 42
    assert kwargs['json']['messages'] == [{'role': 'user', 'content': 'hello'}]
    post.side_effect = requests.Timeout('secret-value')
    assert call_claude('hello') is None
    assert ClaudeApiBackend().run(task).error.kind == 'timeout'


def test_claude_unconnected(task, monkeypatch):
    monkeypatch.setattr(settings, 'claude_api_key', '')
    post = Mock()
    monkeypatch.setattr('app.llm.claude_api.requests.post', post)
    result = ClaudeApiBackend().run(task)
    assert result.error.message == 'unconnected: CLAUDE_API_KEY not set'
    assert result.error.kind == 'backend'
    assert result.raw is None and result.data is None
    assert call_claude('hello') is None
    post.assert_not_called()


def test_api_exception_does_not_expose_key(task, monkeypatch):
    monkeypatch.setattr(settings, 'openai_api_key', 'secret-value')
    monkeypatch.setattr(settings, 'openai_model', 'test')
    monkeypatch.setattr(settings, 'claude_api_key', 'secret-value')
    client = Mock()
    client.chat.completions.create.side_effect = RuntimeError('secret-value')
    monkeypatch.setattr('app.llm.claude_api.requests.post', Mock(side_effect=RuntimeError('secret-value')))
    for backend in (OpenAIApiBackend(client), ClaudeApiBackend()):
        result = backend.run(task)
        assert result.error.kind == 'backend'
        assert 'secret-value' not in result.model_dump_json()
