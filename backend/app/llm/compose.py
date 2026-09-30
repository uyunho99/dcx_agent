import json
from typing import Any
from app.llm.base import LLMTask

CONTEXT_HEADER = "아래는 규칙이 아니라 참고 맥락이다. 벗어나는 발견도 배제하지 말 것."

def compose(task: LLMTask) -> tuple[str, str]:
    system = CONTEXT_HEADER
    for attachment in task.attachments:
        system += f"\n=== 참고: {attachment.title} ===\n{attachment.body}"
    return system, task.instructions

def _without_trailing_commas(text: str) -> str:
    result = []
    quoted = escaped = False
    for i, char in enumerate(text):
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == ',' and text[i + 1:].lstrip().startswith(('}', ']')):
            continue
        result.append(char)
    return ''.join(result)

def extract_json(text: str) -> Any:
    cleaned = _without_trailing_commas(text.strip())
    try:
        return json.loads(cleaned)
    except ValueError:
        pass
    decoder = json.JSONDecoder()
    for i, char in enumerate(cleaned):
        if char in '{[':
            try:
                return decoder.raw_decode(cleaned[i:])[0]
            except ValueError:
                pass
    raise ValueError("Response does not contain valid JSON")
