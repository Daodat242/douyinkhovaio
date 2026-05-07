import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value or ""


@dataclass(frozen=True)
class Settings:
    bot_token: str
    api_id: int
    api_hash: str
    redis_url: str
    admin_user_id: int
    douyin_cookies_b64: str
    download_dir: str
    cookies_path: str
    rate_limit_count: int
    rate_limit_window: int
    max_filesize_mb: int
    cache_ttl: int
    channel_default_limit: int
    channel_max_limit: int
    proxy_url: str


def load_settings() -> Settings:
    return Settings(
        bot_token=_get("BOT_TOKEN", required=True),
        api_id=int(_get("API_ID", "0")),
        api_hash=_get("API_HASH", ""),
        redis_url=_get("REDIS_URL", required=True),
        admin_user_id=int(_get("ADMIN_USER_ID", "0")),
        douyin_cookies_b64=_get("DOUYIN_COOKIES_B64", ""),
        download_dir=_get("DOWNLOAD_DIR", "/tmp/dl"),
        cookies_path=_get("COOKIES_PATH", "/tmp/cookies.txt"),
        rate_limit_count=int(_get("RATE_LIMIT_COUNT", "10")),
        rate_limit_window=int(_get("RATE_LIMIT_WINDOW", "600")),
        max_filesize_mb=int(_get("MAX_FILESIZE_MB", "50")),
        cache_ttl=int(_get("CACHE_TTL", "2592000")),
        channel_default_limit=int(_get("CHANNEL_DEFAULT_LIMIT", "20")),
        channel_max_limit=int(_get("CHANNEL_MAX_LIMIT", "50")),
        proxy_url=_get("PROXY_URL", ""),
    )


settings = load_settings()
