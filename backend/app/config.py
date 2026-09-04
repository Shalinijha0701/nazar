from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    market_provider: Literal["replay", "groww"] = "replay"
    persistence_backend: Literal["memory", "supabase"] = "memory"
    auth_mode: Literal["demo", "supabase"] = "demo"
    demo_token: str = "demo-token"
    groww_access_token: str | None = None
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    allowed_origins: str = (
        "http://localhost:3000,"
        "https://nazar-8lczelyeh-shalinijha1008s-projects.vercel.app"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="NAZAR_",
        extra="ignore",
    )

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    def validate_runtime(self) -> None:
        if self.market_provider == "groww" and not self.groww_access_token:
            raise RuntimeError("NAZAR_GROWW_ACCESS_TOKEN is required for the Groww provider")
        if (self.persistence_backend == "supabase") != (self.auth_mode == "supabase"):
            raise RuntimeError("Supabase persistence and authentication must be enabled together")
        if self.persistence_backend == "supabase" or self.auth_mode == "supabase":
            if not self.supabase_url or not self.supabase_service_role_key:
                raise RuntimeError("Supabase URL and service-role key are required")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime()
    return settings
