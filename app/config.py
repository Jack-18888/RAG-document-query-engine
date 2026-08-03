from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    pinecone_api_key: str
    pinecone_index: str
    deepseek_api_key: str

    deepseek_model: str = "deepseek-v4-flash"
    deepseek_base_url: str = "https://api.deepseek.com"

    upload_dir: str = "data/uploads"
    database_path: str = "data/engine.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
