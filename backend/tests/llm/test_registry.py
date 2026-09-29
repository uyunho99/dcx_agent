from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app.config import settings
from app.llm import registry
from app.llm.base import LLMResult, LLMError
from app.llm.fake import FakeBackend
from app.llm.openai_api import OpenAIApiBackend
from app.llm.compose import CONTEXT_HEADER

def test_retry_once_then_schema_error(task, monkeypatch):
    backend = FakeBackend({task.task: '{"value":"bad"}'})
    backend.run = Mock(wraps=backend.run)
    monkeypatch.setattr(registry, "get_backend", lambda _: backend)
    result = registry.run_task(task)
    assert not result.ok and result.error.kind == "schema"
    assert backend.run.call_count == 2

def test_override_pattern(monkeypatch):
    monkeypatch.setattr(settings, "llm_backend_overrides", {"kw_round_*": "fake"})
    assert isinstance(registry.get_backend("kw_round_2"), FakeBackend)

def test_default_backend_is_openai(task, monkeypatch):
    assert settings.llm_backend == "openai_api"
    assert isinstance(registry.get_backend("kw_round_1"), OpenAIApiBackend)
    client = Mock()
    client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"value":1}'))])
    monkeypatch.setattr(settings, "openai_api_key", "secret-test")
    monkeypatch.setattr(settings, "openai_model", "test-model")
    assert OpenAIApiBackend(client=client).run(task).ok
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["max_completion_tokens"] == task.max_tokens
    assert "max_tokens" not in kwargs
    assert kwargs["response_format"]["type"] == "json_schema"
    assert kwargs["response_format"]["json_schema"]["schema"] == task.output_schema.model_json_schema()
    assert kwargs["messages"][0]["content"].startswith(CONTEXT_HEADER)
    assert kwargs["messages"][1] == {"role":"user", "content":task.instructions}
    for field, env in [("openai_api_key", "OPENAI_API_KEY"), ("openai_model", "OPENAI_MODEL")]:
        with monkeypatch.context() as patch:
            patch.setattr(settings, field, "")
            client.reset_mock()
            result = OpenAIApiBackend(client=client).run(task)
            assert result.error.message == f"unconnected: {env} not set"
            assert result.error.kind == "backend" and result.raw is None and result.data is None
            client.chat.completions.create.assert_not_called()

@pytest.mark.parametrize("kind", ["backend", "timeout", "interrupted"])
def test_terminal_errors_not_retried(task, monkeypatch, kind):
    backend = Mock()
    backend.run.return_value = LLMResult(ok=False, data=None, raw=None, error=LLMError(kind=kind, message="failed"))
    monkeypatch.setattr(registry, "get_backend", lambda _: backend)
    assert registry.run_task(task).error.kind == kind
    assert backend.run.call_count == 1

def test_parse_retry_then_success(task, monkeypatch):
    backend = Mock()
    backend.run.side_effect = [LLMResult(ok=True, raw=raw, data=None, error=None) for raw in ["invalid", '{"value":2}']]
    monkeypatch.setattr(registry, "get_backend", lambda _: backend)
    assert registry.run_task(task).data.value == 2
    assert backend.run.call_count == 2

def test_fake_fixture(task, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "llm_backend", "fake")
    monkeypatch.setattr(FakeBackend, "fixture_dir", tmp_path)
    (tmp_path / "example.json").write_text('{"value":4}')
    assert registry.run_task(task).data.value == 4
