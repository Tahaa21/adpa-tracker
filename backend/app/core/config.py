"""Application settings, sourced from environment variables (.env).

LOCAL_ONLY (default true) is an application-level safeguard, not a network
firewall. With it enabled: browser CORS is force-restricted to localhost
origins regardless of what CORS_ORIGINS is set to, and there are currently
zero configured external integrations anywhere in this codebase (no
telemetry, analytics, error reporting, cloud storage, or AI/LLM calls) —
LOCAL_ONLY exists to keep that true structurally (nothing can silently
enable one via env var) rather than only by omission.

What this does NOT do: CORS is a browser-enforced restriction on which web
origins may call this API from JavaScript — it has no effect on server-to-
server requests, curl, or any non-browser client, and it does nothing to
stop the backend process itself from making an outbound connection if code
were added that did so. LOCAL_ONLY is not an egress firewall and does not
replace one. If you need a hard OS-level guarantee that this machine cannot
send data anywhere, use your OS firewall or run without network access —
see docs/LOCAL_DATA_SECURITY.md for the full, honest breakdown of what is
and isn't guaranteed.
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

    # Application-level local-only safeguard. See module docstring for what
    # this does and does not guarantee. Default TRUE.
    local_only: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if self.local_only:
            # In LOCAL_ONLY mode, silently drop any non-localhost origin
            # rather than trusting env config. This restricts which
            # browser origins may call the API — see module docstring for
            # what this does and does not cover.
            origins = [o for o in origins if _LOCALHOST_ORIGIN_RE.match(o)]
        return origins

    @property
    def max_upload_size_bytes(self) -> int:
        # MiB, not decimal MB: 10 * 1024 * 1024 = 10,485,760 bytes.
        # Pinned by a test (test_upload_size_limit.py) so a future edit
        # that drops one `* 1024` (KB instead of MiB — an easy typo that
        # would silently shrink the real limit to ~10 KB) fails loudly.
        # The comparison at the call site (routers/imports.py) is strict
        # `>`, so a file of exactly this many bytes is accepted, not
        # rejected — "10 MB max" means "up to and including 10 MiB".
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
