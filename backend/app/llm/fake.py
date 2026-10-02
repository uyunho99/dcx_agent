import json
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
                echo = self.fixture_dir / 'segment.dims.echo.json'
                if task.task == 'segment.dims' and echo.exists():
                    path = echo
                raw = path.read_text()
        except (KeyError, OSError):
            return failure('backend', 'Fake response unavailable')
        if task.task == 'segment.dims':
            try:
                echo = json.loads(raw) == {'echo': True}
            except (ValueError, TypeError):
                echo = False
            if echo:
                raw = json.dumps({'items': [dict(doc_id=a.title,
                    environment='여름 실내', internal_state='더위 걱정',
                    task_goal='쾌적한 냉방', activity_response='예약 운전',
                    resource_constraint='전기료 부담') for a in task.attachments]}, ensure_ascii=False)
        return validate(task, raw)
