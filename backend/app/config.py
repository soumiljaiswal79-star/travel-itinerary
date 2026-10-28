from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    groq_api_key: str = ""
    unsplash_access_key: str = ""
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    groq_model: str = "qwen/qwen3.8-27b"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("supabase_url")
    @classmethod
    def normalize_supabase_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        for endpoint_suffix in ("/rest/v1", "/auth/v1"):
            if normalized.endswith(endpoint_suffix):
                normalized = normalized[: -len(endpoint_suffix)]
                break
        return normalized

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
