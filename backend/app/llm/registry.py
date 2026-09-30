from fnmatch import fnmatchcase
from app.config import settings
from app.llm.base import LLMBackend, LLMTask, LLMResult, failure, validate
from app.llm.openai_api import OpenAIApiBackend
from app.llm.claude_api import ClaudeApiBackend
from app.llm.fake import FakeBackend


def get_backend(task_name: str) -> LLMBackend:
    from app.llm.codex_exec import CodexExecBackend
    name = settings.llm_backend
    for pattern, override in settings.llm_backend_overrides.items():
        if fnmatchcase(task_name, pattern):
            name = override
            break
    backends = {'openai_api': OpenAIApiBackend, 'claude_api': ClaudeApiBackend,
                'fake': FakeBackend, 'codex_exec': CodexExecBackend}
    if name not in backends:
        raise ValueError('Unknown LLM backend')
    return backends[name]()


def run_task(task: LLMTask) -> LLMResult:
    try:
        backend = get_backend(task.task)
        for _ in range(2):
            result = backend.run(task)
            if result.ok:
                result = validate(task, result.raw) if result.raw is not None else failure('parse', 'Response has no JSON text')
            if result.ok or result.error.kind not in ('parse', 'schema'):
                return result
        return result
    except Exception:
        return failure('backend', 'LLM backend failed')
