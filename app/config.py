"""Settings read from environment variables (see .env.example)."""
import os
import secrets
from dataclasses import dataclass


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    secret_key: str
    admin_username: str
    admin_password: str
    cookie_secure: bool
    session_hours: int
    timezone: str
    form_slug: str
    db_pool_max: int


def load_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env and fill it in.")
    return Settings(
        database_url=database_url,
        # Used to hash customer IP addresses. Set it so hashes stay stable across restarts.
        secret_key=os.getenv("SECRET_KEY") or secrets.token_hex(32),
        admin_username=os.getenv("ADMIN_USERNAME", "admin").strip().lower(),
        admin_password=os.getenv("ADMIN_PASSWORD", "1234"),
        cookie_secure=_bool("COOKIE_SECURE", True),
        session_hours=int(os.getenv("SESSION_HOURS", "12")),
        timezone=os.getenv("APP_TIMEZONE", "Asia/Karachi"),
        form_slug=os.getenv("FORM_SLUG", "customer-feedback"),
        db_pool_max=int(os.getenv("DB_POOL_MAX", "10")),
    )


settings = load_settings()
