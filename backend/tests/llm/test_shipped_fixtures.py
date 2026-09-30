import pytest
from app.config import settings
from app.context.category import CategoryPath
from app.keywords.prompts import RoundOutput
from app.keywords.rounds import HumanAxes, Suggestions
from app.llm.base import LLMTask
from app.llm.registry import run_task

@pytest.mark.parametrize('task,schema', [(f'kw_round_{n}', RoundOutput) for n in range(1, 5)] + [
    ('category_suggest', CategoryPath), ('kw_suggest_words', Suggestions), ('kw_axis_classify', HumanAxes)])
def test_shipped_fixture_validates(monkeypatch, task, schema):
    monkeypatch.setattr(settings, 'llm_backend', 'fake')
    result = run_task(LLMTask(task=task, sid='fixture', instructions='offline', attachments=[], output_schema=schema))
    assert result.ok, result.error
    assert isinstance(result.data, schema)
