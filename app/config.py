from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    pinecone_api_key: str = Field(alias="PINECONE_API_KEY")
    pinecone_index: str = Field(alias="PINECONE_INDEX")
    deepseek_api_key: str = Field(alias="DEEPSEEK_API_KEY")

    deepseek_model: str = "deepseek-v4-flash"
    deepseek_base_url: str = "https://api.deepseek.com"

    upload_dir: str = "data/uploads"
    database_path: str = "data/engine.db"

    job_max_workers: int = 2
    max_upload_size_mb: int = 50

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
