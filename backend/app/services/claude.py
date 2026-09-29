from pydantic import BaseModel
from app.llm.base import LLMTask
from app.llm.claude_api import ClaudeApiBackend


def call_claude(
    prompt: str,
    max_tokens: int = 2000,
    model: str = "claude-sonnet-4-20250514",
    timeout: int = 60,
) -> str | None:
    """Compatibility entry point for legacy free-text Claude calls."""
    try:
        task = LLMTask(task='legacy_claude', sid='', instructions=prompt,
                       attachments=[], output_schema=BaseModel, max_tokens=max_tokens)
        result = ClaudeApiBackend(model=model, timeout=timeout).generate(task)
        return result.raw if result.ok else None
    except Exception:
        return None
