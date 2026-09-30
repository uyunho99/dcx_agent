from pydantic import BaseModel
from app.config import settings


class Unconnected(Exception):
    pass


class IntegrationStatus(BaseModel):
    name: str
    connected: bool
    env_vars: list[str]
    affects: list[str]
    last_error: str | None = None


INTEGRATIONS = {
    'naver_shopping': ([], ['category_suggest']),
    'naver_searchad': (['SEARCHAD_API_KEY', 'SEARCHAD_SECRET', 'SEARCHAD_CUSTOMER_ID'], ['coverage']),
    'openai': (['OPENAI_API_KEY', 'OPENAI_MODEL'], ['llm']),
    'claude': (['CLAUDE_API_KEY'], ['llm']),
}
LAST_ERRORS: dict[str, str] = {}


def configured(name):
    return str(getattr(settings, name.lower(), '')).strip() not in {'', 'x'}


def integration_status() -> list[IntegrationStatus]:
    return [IntegrationStatus(name=name, connected=name != 'naver_shopping' and all(configured(e) for e in env),
                              env_vars=env, affects=features, last_error='서비스 종료 · 네이버 쇼핑 검색 API는 영구적으로 사용할 수 없습니다.' if name == 'naver_shopping' else LAST_ERRORS.get(name))
            for name, (env, features) in INTEGRATIONS.items()]
