import pytest
from pydantic import BaseModel
from app.llm.base import Attachment, LLMTask

class Answer(BaseModel):
    value: int

@pytest.fixture
def task():
    return LLMTask(task="example", sid="session", instructions="Return JSON", attachments=[Attachment(title="project_context.md", body="# 프로젝트 맥락\n- 제품: LG 휘센 에어컨")], output_schema=Answer)
