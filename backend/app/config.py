from pathlib import Path

from pydantic_settings import BaseSettings

_ENV_FILE = str(Path(__file__).resolve().parents[2] / ".env")


class Settings(BaseSettings):
    # 저장소: "s3" (AWS) 또는 "local" (로컬 디스크)
    storage: str = "s3"
    local_data_dir: str = "data"

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
