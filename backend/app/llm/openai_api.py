from openai import OpenAI, APITimeoutError
from app.config import settings
from app.llm.base import LLMTask, LLMResult, failure, validate
from app.llm.compose import compose

class OpenAIApiBackend:
    def __init__(self, client=None):
        self.client = client

    def run(self, task: LLMTask) -> LLMResult:
        for value, name in [(settings.openai_api_key, 'OPENAI_API_KEY'), (settings.openai_model, 'OPENAI_MODEL')]:
            if not value:
                return failure('backend', f'unconnected: {name} not set')
        system, user = compose(task)
        try:
            if self.client is None:
                self.client = OpenAI(api_key=settings.openai_api_key, max_retries=0)
            response = self.client.chat.completions.create(
                model=settings.openai_model,
                max_tokens=task.max_tokens,
                messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
                response_format={'type': 'json_schema', 'json_schema': {
                    'name': task.output_schema.__name__,
                    'schema': task.output_schema.model_json_schema(),
                }},
            )
            raw = response.choices[0].message.content
        except APITimeoutError:
            return failure('timeout', 'OpenAI request timed out')
        except Exception:
            return failure('backend', 'OpenAI request failed')
        return validate(task, raw)
