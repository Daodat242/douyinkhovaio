import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.types import FSInputFile, Message

from src.config import settings
from src.services import downloader
from src.services.cache import CachedFile, FileCache
from src.services.ratelimit import RateLimiter
from src.services.url_parser import parse_message

log = logging.getLogger(__name__)

router = Router(name="video")


def _format_caption(title: str, uploader: str) -> str:
    title = title.strip()[:200] or "video"
    return f"🎬 <b>{title}</b>\n👤 {uploader}"


@router.message(F.text.regexp(r"https?://"))
async def on_url(message: Message, cache: FileCache, limiter: RateLimiter) -> None:
    if not message.text:
        return

    parsed = parse_message(message.text)
    if not parsed or not parsed.is_supported:
        await message.reply(
            "❌ Link không hợp lệ. Tao chỉ nhận link Douyin hoặc TikTok.\n"
            "Gõ /help để xem định dạng được hỗ trợ."
        )
        return

    user_id = message.from_user.id if message.from_user else 0

    rl = await limiter.hit(user_id)
    if not rl.allowed:
        minutes = (rl.retry_after + 59) // 60
        await message.reply(
            f"⏳ Mày đã tải {rl.used - 1}/{rl.limit} video trong cửa sổ hiện tại. "
            f"Quay lại sau {minutes} phút nữa."
        )
        return

    if parsed.is_user:
        await message.reply(
            "📺 Link kênh — tính năng tải nguyên kênh đang phát triển (Phase 3). "
            "Hiện tại chỉ hỗ trợ link 1 video."
        )
        return

    cached = await cache.get(parsed.canonical)
    if cached:
        log.info("cache hit user=%s url=%s", user_id, parsed.canonical)
        await message.reply_video(
            video=cached.file_id,
            caption=_format_caption(cached.title, cached.uploader),
        )
        return

    status = await message.reply("⏬ Đang tải, chờ chút...")

    try:
        result = await downloader.download(
            parsed.canonical,
            Path(settings.download_dir),
            settings.cookies_path,
            settings.max_filesize_mb,
        )
    except downloader.TooLargeError as exc:
        await status.edit_text(
            f"⚠️ Video {exc.size_mb:.1f}MB vượt giới hạn {exc.limit_mb}MB của Bot API. "
            "Chức năng gửi file lớn (đến 2GB) sẽ ra mắt ở Phase 2."
        )
        return
    except downloader.DownloadError as exc:
        log.warning("download failed url=%s err=%s", parsed.canonical, exc)
        err_text = str(exc).lower()
        if "fresh cookies" in err_text or "login" in err_text:
            reply = (
                "🍪 Douyin đang chặn (cookies cần refresh hoặc IP server bị khoá). "
                "Admin đang xử lý — thử lại sau, hoặc gửi link TikTok thay thế."
            )
        elif "private" in err_text or "unavailable" in err_text:
            reply = "🔒 Video riêng tư hoặc đã bị xoá."
        else:
            reply = (
                "❌ Không tải được video. Có thể link đã hết hạn, video bị xoá, "
                "hoặc Douyin chặn. Thử lại sau hoặc gửi link khác."
            )
        await status.edit_text(reply)
        return
    except Exception as exc:
        log.exception("unexpected error url=%s", parsed.canonical)
        await status.edit_text(f"💥 Lỗi không mong muốn: {exc}")
        return

    try:
        sent = await message.reply_video(
            video=FSInputFile(result.filepath),
            caption=_format_caption(result.info.title, result.info.uploader),
            supports_streaming=True,
            duration=result.info.duration or None,
        )
        await status.delete()

        if sent.video:
            await cache.set(
                parsed.canonical,
                CachedFile(
                    file_id=sent.video.file_id,
                    title=result.info.title,
                    uploader=result.info.uploader,
                ),
            )
    finally:
        downloader.cleanup_file(result.filepath)
