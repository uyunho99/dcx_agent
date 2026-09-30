from pathlib import Path
from app.llm.base import LLMTask, LLMResult, failure, validate
from app.llm.compose import compose

class FakeBackend:
    fixture_dir = Path(__file__).resolve().parents[2] / 'tests/fixtures/llm'

    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses

    def run(self, task: LLMTask) -> LLMResult:
        compose(task)
        try:
            if self.responses is not None:
                raw = self.responses[task.task]
            else:
                path = (self.fixture_dir / f'{task.task}.json').resolve()
                if not path.is_relative_to(self.fixture_dir.resolve()):
                    return failure('backend', 'Invalid fixture name')
                raw = path.read_text()
        except (KeyError, OSError):
            return failure('backend', 'Fake response unavailable')
        return validate(task, raw)
