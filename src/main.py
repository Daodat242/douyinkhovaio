import asyncio
import logging
import shutil
from pathlib import Path

import redis.asyncio as redis
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from src.config import settings
from src.handlers import start as start_handler
from src.handlers import video as video_handler
from src.services import downloader
from src.services.cache import FileCache
from src.services.ratelimit import RateLimiter

log = logging.getLogger(__name__)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


def _prepare_filesystem() -> None:
    download_dir = Path(settings.download_dir)
    if download_dir.exists():
        shutil.rmtree(download_dir, ignore_errors=True)
    download_dir.mkdir(parents=True, exist_ok=True)
    log.info("Prepared download dir: %s", download_dir)


def _redact_proxy(url: str) -> str:
    """Ẩn user:pass trong proxy URL khi log."""
    if "@" in url:
        scheme_split = url.split("://", 1)
        if len(scheme_split) == 2 and "@" in scheme_split[1]:
            return f"{scheme_split[0]}://***@{scheme_split[1].split('@', 1)[1]}"
    return url


async def _connect_redis_with_retry(url: str) -> redis.Redis:
    """Railway boots services in parallel — Redis DNS có thể chưa sẵn sàng
    khi bot start. Retry với exponential backoff."""
    delays = [2, 4, 8, 16, 30]
    last_exc: Exception | None = None
    for attempt, delay in enumerate(delays, start=1):
        try:
            client: redis.Redis = redis.from_url(url, decode_responses=True)
            await client.ping()
            log.info("Connected to Redis (attempt %d)", attempt)
            return client
        except Exception as exc:
            last_exc = exc
            log.warning(
                "Redis connect failed (attempt %d/%d): %s — retry sau %ds",
                attempt,
                len(delays),
                exc,
                delay,
            )
            await asyncio.sleep(delay)
    raise RuntimeError(f"Redis unreachable sau {len(delays)} lần thử: {last_exc}")


async def _run() -> None:
    _configure_logging()
    _prepare_filesystem()

    log.info(
        "Provider chain: %s",
        " → ".join(name for name, _ in downloader._PROVIDERS),
    )
    log.info("douyin.wtf endpoint: %s", downloader._DOUYIN_WTF_BASE)
    if downloader._DOUYIN_WTF_BASE == "https://api.douyin.wtf":
        log.warning(
            "Đang dùng public demo api.douyin.wtf — README ghi 'fragile'. "
            "Self-host và set DOUYIN_WTF_ENDPOINT để stable."
        )
    if settings.proxy_url:
        log.info("Routing requests via proxy: %s", _redact_proxy(settings.proxy_url))

    redis_client = await _connect_redis_with_retry(settings.redis_url)

    cache = FileCache(redis_client, ttl=settings.cache_ttl)
    limiter = RateLimiter(
        redis_client,
        limit=settings.rate_limit_count,
        window_seconds=settings.rate_limit_window,
    )

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp["cache"] = cache
    dp["limiter"] = limiter
    dp.include_router(start_handler.router)
    dp.include_router(video_handler.router)

    me = await bot.get_me()
    log.info("Bot @%s started (id=%s)", me.username, me.id)

    webhook_info = await bot.get_webhook_info()
    if webhook_info.url:
        log.info("Removing existing webhook: %s", webhook_info.url)
    await bot.delete_webhook(drop_pending_updates=True)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        await redis_client.close()


def main() -> None:
    try:
        asyncio.run(_run())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot stopped")


if __name__ == "__main__":
    main()
