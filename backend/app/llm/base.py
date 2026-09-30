from typing import Literal, Protocol
from pydantic import BaseModel, ValidationError

class Attachment(BaseModel):
    title: str
    body: str

class LLMTask(BaseModel):
    task: str
    sid: str
    instructions: str
    attachments: list[Attachment]
    output_schema: type[BaseModel]
    max_tokens: int = 8000

class LLMError(BaseModel):
    kind: Literal["timeout", "parse", "schema", "backend", "interrupted"]
    message: str

class LLMResult(BaseModel):
    ok: bool
    data: BaseModel | None = None
    raw: str | None = None
    error: LLMError | None = None

class LLMBackend(Protocol):
    def run(self, task: LLMTask) -> LLMResult: ...

def failure(kind, message):
    return LLMResult(ok=False, error=LLMError(kind=kind, message=message))

def validate(task: LLMTask, raw: str) -> LLMResult:
    from app.llm.compose import extract_json
    try:
        value = extract_json(raw)
    except (ValueError, TypeError):
        return failure("parse", "Response does not contain valid JSON")
    try:
        data = task.output_schema.model_validate(value)
    except ValidationError:
        return failure("schema", "Response does not match output schema")
    return LLMResult(ok=True, data=data, raw=raw)
