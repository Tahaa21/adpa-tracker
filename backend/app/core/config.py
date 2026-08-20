"""Application settings, sourced from environment variables (.env).

LOCAL_ONLY (default true) is a hard guarantee for this MVP: with it enabled,
the app never initializes any outbound network integration and CORS is
force-restricted to localhost origins regardless of what CORS_ORIGINS is set
to. There are currently zero external integrations in this codebase (no
telemetry, analytics, error reporting, or AI/LLM calls) — LOCAL_ONLY exists
to keep it that way structurally, not just by omission. See
docs/LOCAL_DATA_SECURITY.md.
"""
import re
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

_LOCALHOST_ORIGIN_RE = re.compile(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./app.db"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    max_upload_size_mb: int = 10

    # Hard local-only guarantee. See module docstring. Default TRUE.
    local_only: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if self.local_only:
            # In LOCAL_ONLY mode, silently drop any non-localhost origin
            # rather than trusting env config — this is a hard guarantee,
            # not a suggestion.
            origins = [o for o in origins if _LOCALHOST_ORIGIN_RE.match(o)]
        return origins

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
