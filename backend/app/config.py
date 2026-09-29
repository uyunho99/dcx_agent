from pathlib import Path

from pydantic_settings import BaseSettings

_ENV_FILE = str(Path(__file__).resolve().parents[2] / ".env")


class Settings(BaseSettings):
    # 저장소: "s3" (AWS) 또는 "local" (로컬 디스크)
    storage: str = "local"
    local_data_dir: str = "data"

    llm_backend: str = "openai_api"
    openai_api_key: str = ""
    openai_model: str = ""
    llm_backend_overrides: dict[str, str] = {}
    codex_bin: str = "codex"
    codex_profile: str = "dcx-worker"
    codex_timeout_s: int = 600
    claude_model: str = "claude-sonnet-4-20250514"
    naver_search_base_url: str = "https://openapi.naver.com"
    searchad_api_key: str = ""
    searchad_secret: str = ""
    searchad_customer_id: str = ""
    youtube_api_key: str = ""
    fixture_corpus_path: str = ""
    enable_fixture_channel: bool = False
    real_channels_enabled: bool = True
    low_volume_threshold: int = 10
    gate_low_count: int = 10
    gate_low_unique: float = 0.2
    author_salt_path: str = "data/.author_salt"

    s3_bucket: str = "x"
    s3_region: str = "x"
    naver_client_id: str = "x"
    naver_client_secret: str = "x"
    claude_api_key: str = "x"
    pinecone_api_key: str = "x"
    voyage_api_key: str = "x"

    # 배포 설정
    cors_origins: str = "*"  # 프로덕션: "https://your-domain.com"

    class Config:
        env_file = _ENV_FILE


settings = Settings()
