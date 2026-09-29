import requests
from app.config import settings
from app.llm.base import LLMTask, LLMResult, failure, validate
from app.llm.compose import compose

CLAUDE_URL = 'https://api.anthropic.com/v1/messages'

class ClaudeApiBackend:
    def __init__(self, model=None, timeout=60):
        self.model = model
        self.timeout = timeout

    def generate(self, task: LLMTask) -> LLMResult:
        """Compose a new task before requesting raw text."""
        system, user = compose(task)
        return self.generate_text(user, task.max_tokens, system=system)

    def generate_text(self, prompt: str, max_tokens: int, *, system: str | None = None) -> LLMResult:
        """Shared transport; omit system entirely for legacy free-text calls."""
        if not settings.claude_api_key:
            return failure('backend', 'unconnected: CLAUDE_API_KEY not set')
        payload = {'model': self.model or settings.claude_model, 'max_tokens': max_tokens,
                   'messages': [{'role': 'user', 'content': prompt}]}
        if system is not None:
            payload['system'] = system
        try:
            response = requests.post(
                CLAUDE_URL,
                headers={'x-api-key': settings.claude_api_key, 'anthropic-version': '2023-06-01', 'Content-Type': 'application/json'},
                json=payload,
                timeout=self.timeout,
            )
            if response.status_code != 200:
                return failure('backend', 'Claude request failed')
            raw = response.json()['content'][0]['text']
            return LLMResult(ok=True, raw=raw)
        except requests.Timeout:
            return failure('timeout', 'Claude request timed out')
        except Exception:
            return failure('backend', 'Claude request failed')

    def run(self, task: LLMTask) -> LLMResult:
        result = self.generate(task)
        return validate(task, result.raw) if result.ok else result
