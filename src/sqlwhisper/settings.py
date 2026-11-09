from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from env vars or `.env`. Field name = var name, case-insensitive."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    ollama_timeout_s: int = Field(60, gt=0)

    max_rows: int = Field(500, gt=0)
    max_retries: int = Field(2, ge=0)
    query_timeout_s: int = Field(15, gt=0)

    max_upload_mb: int = Field(50, gt=0)
    data_dir: Path = Path("data")

    api_url: str = "http://localhost:8000"
