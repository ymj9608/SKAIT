from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Re:Class API"
    app_version: str = "0.2.0"
    stt_provider: str = "demo"
    llm_provider: str = "local"
    hf_token: str | None = None
    hf_stt_model: str = "openai/whisper-large-v3"
    hf_llm_model: str = "openai/gpt-oss-120b:fastest"
    local_whisper_model: str = "small"
    mlx_whisper_model: str = "mlx-community/whisper-large-v3-turbo"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:8b"
    ollama_timeout_seconds: float = 180
    ollama_context_window: int = 8192
    ollama_keep_alive: str = "15m"
    learning_item_batch_seconds: int = Field(default=30, ge=15, le=60)
    summary_batch_seconds: int = Field(default=120, ge=30, le=600)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    database_file: Path = Path("data/reclass.sqlite3")
    # 이전 버전의 JSON 기록을 최초 한 번 가져오기 위한 경로입니다.
    # DATA_FILE 환경변수 이름은 기존 사용자의 설정과 호환되도록 유지합니다.
    data_file: Path = Path("data/sessions.json")
    max_audio_mb: int = 25

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @field_validator("stt_provider")
    @classmethod
    def validate_stt_provider(cls, value: str) -> str:
        value = value.lower().strip()
        if value not in {"demo", "huggingface", "faster_whisper", "mlx_whisper"}:
            raise ValueError(
                "STT_PROVIDER는 demo, huggingface, faster_whisper, mlx_whisper 중 하나여야 합니다."
            )
        return value

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, value: str) -> str:
        value = value.lower().strip()
        if value not in {"local", "huggingface", "ollama"}:
            raise ValueError("LLM_PROVIDER는 local, huggingface, ollama 중 하나여야 합니다.")
        return value

    @field_validator("ollama_base_url")
    @classmethod
    def normalize_ollama_base_url(cls, value: str) -> str:
        return value.strip().rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
