from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_core import PydanticUseDefault

from pydantic_settings import BaseSettings, NoDecode

_ENV_FILE = str(Path(__file__).resolve().parents[2] / ".env")


class Settings(BaseSettings):
    # 저장소: "s3" (AWS) 또는 "local" (로컬 디스크)
    storage: str = "local"
    local_data_dir: str = "data"

    keyword_locked_rounds: list[int] = [2]

    llm_backend: str = "openai_api"
    openai_api_key: str = ""
    openai_model: str = ""
    llm_backend_overrides: dict[str, str] = {}
    codex_bin: str = "codex"
    codex_profile: str = "dcx-worker"
    codex_timeout_s: int = 600
    claude_model: str = "claude-sonnet-4-20250514"
    naver_search_base_url: str = "https://openapi.naver.com"
    autocomplete_backend: Literal["http", "fake"] = "http"
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
    voyage_api_key: str = "x"

    embed_backend: Literal["voyage", "fake"] = "voyage"
    embed_model: str = "voyage-4"
    embed_dim: int = 1024
    jev_api_keys: Annotated[list[str], NoDecode] = Field(default_factory=list, validation_alias="JEVMODEL_API_KEY")
    jev_model: str = "jev-latest"
    jev_rate_per_min: int = 120
    jev_backend: Literal["http", "fake"] = "http"
    label_gpt_backend: Literal["codex_exec", "openai_api", "fake"] = "codex_exec"
    label_fake_jev_cross: bool = False
    label_batch_size: int = 20
    label_concurrency: int = 4
    segment_concurrency: int = 4
    evidence_llm_concurrency: int = 4
    known_theta: float = 0.85
    model_cut_low: float = 0.2
    model_cut_high: float = 0.8
    monitor_rate: float = 0.01
    monitor_warn: float = 0.15
    head_min_samples: int = 30
    audit_first: int = 1000
    audit_every: int = 10000
    audit_size: int = 50
    audit_reissue: int = 2
    kappa_floor: float = 0.75

    @field_validator(
        "embed_backend", "embed_model", "embed_dim", "jev_model", "jev_rate_per_min",
        "jev_backend", "label_gpt_backend", "label_fake_jev_cross", "label_batch_size", "label_concurrency", "segment_concurrency",
        "known_theta", "model_cut_low", "model_cut_high", "monitor_rate", "monitor_warn",
        "head_min_samples", "audit_first", "audit_every", "audit_size", "audit_reissue",
        "kappa_floor", mode="before",
    )
    @classmethod
    def empty_stage_setting_uses_default(cls, value):
        if value == "":
            raise PydanticUseDefault()
        return value

    @field_validator("jev_api_keys", mode="before")
    @classmethod
    def split_jev_keys(cls, value):
        if isinstance(value, str):
            return [key.strip() for key in value.split(",") if key.strip()]
        return value

    # 배포 설정
    cors_origins: str = "*"  # 프로덕션: "https://your-domain.com"

    class Config:
        env_file = _ENV_FILE
        extra = 'ignore'


settings = Settings()
