# Douyin Telegram Downloader Bot — Plan

Tổng hợp lại từ đoạn chat, sắp lại theo thứ tự thực thi để build từ MVP → bot production-ready.

## 1. Mục tiêu

Bot Telegram cho phép user dán link Douyin → bot trả về file video không watermark.
Hỗ trợ 2 loại input:
- Link 1 video đơn lẻ (`v.douyin.com/xxx` hoặc link đầy đủ).
- Link kênh/user Douyin (`douyin.com/user/MS4w...`) → tải N video mới nhất.

## 2. Kiến trúc & các thành phần phải kết nối

```
User (Telegram)
   │  message: link Douyin
   ▼
Telegram Bot API  ──►  Bot worker (Python, aiogram/python-telegram-bot)
                              │
                              ├─► Validator (check là link Douyin? video hay channel?)
                              │
                              ├─► Queue (Redis) ──► Worker pool (Celery / asyncio)
                              │                          │
                              │                          ▼
                              │                       yt-dlp  (tải video không watermark)
                              │                          │
                              │                          ▼
                              │                       Local tmp file
                              │                          │
                              ▼                          ▼
                       Telegram Bot API / Pyrogram (MTProto)  ──► gửi file về user
                                                              ──► xoá file local
```

4 mảnh phải có:
1. **Telegram Bot** — tạo qua `@BotFather`, lấy `BOT_TOKEN`.
2. **Library Telegram** — `aiogram` (async, gọn) cho phần bot logic. **Pyrogram** (MTProto) cho phần upload file > 50MB.
3. **yt-dlp** — tool tải video Douyin (gồm cả channel listing).
4. **Hosting** — Railway (đã có).
5. **Redis** — addon Railway, dùng làm queue + lưu state (cần khi user gửi link channel có hàng trăm video).

## 3. Roadmap theo phase

### Phase 0 — Setup (0.5 ngày)
- [ ] `@BotFather` tạo bot, lấy `BOT_TOKEN`.
- [ ] Đăng ký `api_id` + `api_hash` ở https://my.telegram.org (cần cho Pyrogram để vượt 50MB).
- [ ] Khởi tạo project Python: `pyproject.toml` / `requirements.txt`.
  - `aiogram`, `pyrogram`, `tgcrypto`, `yt-dlp`, `redis`, `celery` (hoặc `arq`), `python-dotenv`.
- [ ] `.env`: `BOT_TOKEN`, `API_ID`, `API_HASH`, `REDIS_URL`, `DOWNLOAD_DIR=/tmp/dl`.
- [ ] `Procfile` / `railway.json` cho Railway.

### Phase 1 — MVP: 1 link → 1 video (1 ngày)
- [ ] Bot lắng nghe `/start`, `/help` và message text.
- [ ] Regex validate link Douyin (`v.douyin.com`, `douyin.com/video`, `douyin.com/user`).
- [ ] Hàm `download_video(url) -> filepath` dùng `yt-dlp` với options:
  ```python
  ydl_opts = {
      "outtmpl": f"{DOWNLOAD_DIR}/%(id)s.%(ext)s",
      "format": "best[filesize<50M]/best",
      "noplaylist": True,
      "quiet": True,
  }
  ```
- [ ] Sau khi tải: gửi qua Telegram → xoá file ngay (`os.remove` trong `finally`).
- [ ] Try/except cho: link die, video xoá, network timeout.

### Phase 2 — Vượt 50MB (1–2 ngày, **đây là phần khó nhất**)
Chọn **Pyrogram (MTProto)**, lý do: upload tới 2GB, không cần self-host Bot API server, không phải nén mất chất lượng.
- [ ] Tách 2 client:
  - `aiogram` Bot — nhận lệnh, trả status text.
  - `pyrogram` Client (chạy bằng cùng `BOT_TOKEN`) — chuyên upload file lớn.
- [ ] Logic gửi file:
  - File < 50MB → gửi qua aiogram cho nhanh.
  - File ≥ 50MB → gửi qua Pyrogram.
- [ ] Giới hạn cứng `MAX_FILESIZE_MB=1900` để tránh upload ngược timeout.

### Phase 3 — Channel / batch download (1–2 ngày)
- [ ] Detect link là user/channel → dùng `yt_dlp.extract_info(url, download=False)` để lấy số lượng video.
- [ ] Hỏi lại user: "Kênh có **N** video. Tải bao nhiêu cái mới nhất? (mặc định 20, max 50)".
  - Dùng inline keyboard: `10 / 20 / 50 / Huỷ`.
- [ ] Đẩy job vào Redis queue, mỗi video là 1 task.
- [ ] Worker pool song song **tối đa 2** (nhiều hơn dễ bị Douyin ban IP).
- [ ] `yt-dlp` options:
  ```python
  {
      "playlistend": N,
      "sleep_interval": 3,
      "max_sleep_interval": 7,
      "outtmpl": "{DOWNLOAD_DIR}/%(uploader)s/%(id)s.%(ext)s",
  }
  ```
- [ ] Mỗi video tải xong → gửi luôn → xoá file → tải tiếp (KHÔNG batch).
- [ ] Báo tiến độ: edit 1 message duy nhất `"Đã tải 7/20 ..."`, không spam.

### Phase 4 — Anti-block Douyin (chạy song song Phase 3)
- [ ] Set User-Agent + headers Douyin chuẩn (`http_headers` trong yt-dlp).
- [ ] Cookie file: export cookie Douyin từ trình duyệt → `cookies.txt` → mount vào Railway secret/volume.
- [ ] Sleep interval giữa các request (đã có ở Phase 3).
- [ ] Retry với exponential backoff: 3 lần, 5s → 15s → 45s.
- [ ] Job để auto `pip install -U yt-dlp` định kỳ (Railway cron, hoặc rebuild image hàng tuần).
- [ ] (Optional) Proxy: nếu bị region-lock, cấu hình `proxy` trong yt-dlp. Residential CN proxy đắt — chỉ làm khi thật cần.

### Phase 5 — Storage & bandwidth control trên Railway
- [ ] Disk Railway là ephemeral → đảm bảo flow `download → send → delete` luôn chạy trong `try/finally`.
- [ ] `DOWNLOAD_DIR` = `/tmp/dl`, dọn rác lúc startup (`shutil.rmtree`).
- [ ] Quota per user: ví dụ tối đa 10 video / 10 phút (lưu counter trong Redis với TTL).
- [ ] Theo dõi egress bandwidth Railway → set alert ở mức 80% credit.
- [ ] Log từng request (user_id, url, size, duration) để biết user nào đốt nhiều băng thông.

### Phase 6 — Polish & ops
- [ ] `/cancel` để huỷ job đang chạy của chính mình.
- [ ] `/stats` (admin) — tổng số video đã tải, dung lượng, top user.
- [ ] Sentry (hoặc log file đơn giản) cho exception.
- [ ] README.md hướng dẫn deploy.
- [ ] Healthcheck endpoint cho Railway.

## 4. Cấu trúc thư mục đề xuất

```
douyinkhovaio/
├── PLAN.md                  ← file này
├── README.md
├── pyproject.toml
├── railway.json
├── .env.example
├── src/
│   ├── __init__.py
│   ├── main.py              ← entrypoint, khởi tạo aiogram + pyrogram
│   ├── config.py            ← load env
│   ├── handlers/
│   │   ├── start.py
│   │   ├── single_video.py
│   │   └── channel.py
│   ├── services/
│   │   ├── downloader.py    ← wrapper yt-dlp
│   │   ├── uploader.py      ← chọn aiogram vs pyrogram theo size
│   │   └── url_parser.py    ← detect video vs channel
│   ├── queue/
│   │   ├── worker.py        ← celery/arq worker
│   │   └── tasks.py
│   └── utils/
│       ├── ratelimit.py
│       └── cleanup.py
└── tests/
```

## 5. Risk register (sắp theo độ khó, từ chat)

| # | Rủi ro | Mức độ | Hướng xử lý |
|---|---|---|---|
| 1 | Telegram Bot API giới hạn 50MB | **Cao** | Dùng Pyrogram MTProto |
| 2 | Douyin chống bot (cookie, rate-limit, region-lock) | **Cao** | Cookie file, sleep interval, update yt-dlp định kỳ, proxy (nếu cần) |
| 3 | Bandwidth/storage Railway đốt credit nhanh | Trung bình | Quota per user, ephemeral cleanup, alert |
| 4 | Channel có hàng trăm video → block bot | Trung bình | Queue + giới hạn cứng N video / lần |
| 5 | yt-dlp break do Douyin đổi API | Trung bình | Auto update job hàng tuần |
| 6 | Bản quyền / TOS Douyin & Telegram | Thấp–TB | Bot chỉ chia sẻ trong nhóm tin cậy, không public quá rộng |

## 6. Câu hỏi cần mày chốt trước khi code

1. Bot dùng **public** (ai cũng add) hay **private** (whitelist user_id)? → ảnh hưởng quota & risk.
2. Có cần lưu video lên storage ngoài (S3/R2) để tránh tải lại không, hay luôn tải mới?
3. Channel download: max bao nhiêu video / lần tao set cứng? (chat đề xuất 20, mày muốn cao hơn?)
4. Có muốn hỗ trợ thêm TikTok / YouTube Shorts luôn không? (yt-dlp làm được hết, gần như free).

## 7. Bước tiếp theo đề xuất

Bắt đầu từ **Phase 0 + Phase 1** để có MVP chạy được trong 1 ngày, rồi mới đụng Pyrogram (Phase 2). Đừng làm queue/channel ngay, dễ overengineer khi chưa có user thật.
