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
from src.services.cache import FileCache
from src.services.cookies import write_cookies_from_env
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


async def _run() -> None:
    _configure_logging()
    _prepare_filesystem()
    write_cookies_from_env(settings.douyin_cookies_b64, settings.cookies_path)

    redis_client: redis.Redis = redis.from_url(
        settings.redis_url, decode_responses=True
    )
    await redis_client.ping()
    log.info("Connected to Redis")

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
