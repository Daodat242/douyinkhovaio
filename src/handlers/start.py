from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

router = Router(name="start")


WELCOME = (
    "👋 Chào mày! Tao là bot tải video Douyin / TikTok không watermark.\n\n"
    "Cách dùng: dán link video Douyin hoặc TikTok vào đây, tao sẽ tải về và gửi lại cho mày.\n\n"
    "Lệnh:\n"
    "/start — xem hướng dẫn này\n"
    "/help — chi tiết hơn"
)

HELP = (
    "📖 <b>Hướng dẫn sử dụng</b>\n\n"
    "<b>Hỗ trợ:</b>\n"
    "• Douyin: <code>v.douyin.com/...</code>, <code>douyin.com/video/...</code>\n"
    "• TikTok: <code>vm.tiktok.com/...</code>, <code>tiktok.com/@user/video/...</code>\n\n"
    "<b>Giới hạn hiện tại:</b>\n"
    "• File tối đa 50MB (đang phát triển bản 2GB qua Pyrogram)\n"
    "• Tối đa 10 video / 10 phút / user\n"
    "• Tải nguyên kênh: sắp ra mắt (Phase 3)\n\n"
    "Báo lỗi: nhắn admin."
)


@router.message(CommandStart())
async def on_start(message: Message) -> None:
    await message.answer(WELCOME)


@router.message(Command("help"))
async def on_help(message: Message) -> None:
    await message.answer(HELP)
