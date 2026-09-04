from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    mode: str = "replay"
    market_provider: str = "replay"
    persistence: str = "memory"
    auth_mode: str = "demo"
    groww_access_token: str | None = None
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    allowed_origins: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="NAZAR_",
        extra="ignore",
    )

    @property
    def origins(self) -> list[str]:
        return [value.strip() for value in self.allowed_origins.split(",") if value.strip()]

    def model_post_init(self, __context: object) -> None:
        # Keep the original one-variable demo configuration backwards compatible.
        if self.mode == "live":
            if self.market_provider == "replay":
                self.market_provider = "groww"
            if self.persistence == "memory":
                self.persistence = "supabase"
            if self.auth_mode == "demo":
                self.auth_mode = "supabase"


@lru_cache
def get_settings() -> Settings:
    return Settings()
