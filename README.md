# Douyin / TikTok Telegram Downloader Bot

Bot Telegram tải video Douyin & TikTok không watermark.

Trạng thái hiện tại: **Phase 0 + 1 (MVP)** — xem [PLAN.md](PLAN.md) cho roadmap đầy đủ.

## Tính năng MVP

- Dán link Douyin / TikTok → bot trả về file video.
- Cache `file_id` qua Redis: lần thứ 2 ai gửi cùng link → gửi tức thì, không tải lại.
- Rate limit per user (mặc định 10 video / 10 phút) vì là bot public.
- Cookies Douyin nạp từ env var (base64) lúc startup.
- Auto-clean file tải về sau khi gửi xong.

## Stack

- Python 3.11
- [aiogram 3](https://docs.aiogram.dev/) (async Telegram bot)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (download engine)
- Redis (cache + rate limit)
- Railway (hosting)

## Cấu trúc

```
src/
├── main.py                 # entrypoint
├── config.py               # load env
├── handlers/
│   ├── start.py            # /start, /help
│   └── video.py            # xử lý link
└── services/
    ├── url_parser.py       # detect Douyin/TikTok URL
    ├── downloader.py       # yt-dlp wrapper
    ├── cache.py            # file_id cache (Redis)
    ├── ratelimit.py        # rate limit (Redis)
    └── cookies.py          # decode cookies từ env
```

## Setup local

```bash
git clone <repo>
cd douyinkhovaio
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Sửa .env với giá trị thật của mày
python -m src.main
```

## Deploy Railway

1. Push code lên GitHub.
2. Railway → New Project → Deploy from GitHub → chọn repo này.
3. Add Redis service (Database → Redis), copy `REDIS_URL` vào env.
4. Set tất cả biến từ `.env.example` trong tab Variables.
5. Encode cookies Douyin và set `DOUYIN_COOKIES_B64`:
   ```bash
   cat cookies.txt | base64 -w0
   ```
6. Deploy. Logs sẽ thấy `Bot @yourbot started`.

## Env vars bắt buộc

| Tên | Lấy ở đâu |
|---|---|
| `BOT_TOKEN` | `@BotFather` → `/newbot` |
| `API_ID`, `API_HASH` | https://my.telegram.org (Phase 2) |
| `REDIS_URL` | Railway Redis addon |
| `ADMIN_USER_ID` | `@userinfobot` |
| `DOUYIN_COOKIES_B64` | Export cookies.txt từ trình duyệt → `base64 -w0` |

## Roadmap

Xem [PLAN.md](PLAN.md). Phase tiếp theo: **Pyrogram MTProto** để vượt giới hạn 50MB.

## Cảnh báo bảo mật

- **KHÔNG** commit `.env`, `cookies.txt`, hoặc bất kỳ file nào chứa session/token.
- File `.gitignore` đã chặn các file nhạy cảm.
- Cookie Douyin chứa session login — coi như mật khẩu.
