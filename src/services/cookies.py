import base64
import logging
import os
import time
from pathlib import Path

log = logging.getLogger(__name__)

# Douyin extractor của yt-dlp kiểm tra các cookie này. Hết hạn → "Fresh
# cookies needed" error.
_CRITICAL_DOUYIN_COOKIES = ("sessionid", "ttwid", "passport_csrf_token")


def _check_cookie_freshness(cookie_text: str) -> None:
    """Parse Netscape cookie file, log warning nếu cookies quan trọng đã hết
    hạn hoặc sắp hết hạn (< 24h). Giúp phân biệt lỗi cookies expired vs
    anti-bot block khi debug."""
    now = int(time.time())
    found: dict[str, int] = {}

    for line in cookie_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split("\t")
        if len(parts) < 7:
            continue
        try:
            expiry = int(parts[4])
        except ValueError:
            continue
        name = parts[5]
        if name in _CRITICAL_DOUYIN_COOKIES:
            found[name] = expiry

    for name in _CRITICAL_DOUYIN_COOKIES:
        if name not in found:
            log.warning("Cookie '%s' không có trong file — Douyin có thể từ chối", name)
            continue
        expiry = found[name]
        if expiry == 0:
            log.info("Cookie '%s' là session cookie (no expiry)", name)
            continue
        remaining = expiry - now
        if remaining <= 0:
            log.error(
                "Cookie '%s' ĐÃ HẾT HẠN %d giờ trước — export lại từ browser",
                name,
                -remaining // 3600,
            )
        elif remaining < 86400:
            log.warning(
                "Cookie '%s' sắp hết hạn (%d giờ nữa)",
                name,
                remaining // 3600,
            )
        else:
            log.info("Cookie '%s' còn hạn %d ngày", name, remaining // 86400)


def write_cookies_from_env(b64_content: str, target_path: str) -> str | None:
    """Decode base64 cookie blob from env and write to disk for yt-dlp to consume.

    Returns the path on success, or None if no cookies were provided.
    """
    if not b64_content:
        log.info("DOUYIN_COOKIES_B64 not set — yt-dlp will run without cookies")
        return None

    cleaned = "".join(b64_content.split())
    padding = (-len(cleaned)) % 4
    if padding:
        cleaned += "=" * padding

    try:
        decoded_bytes = base64.b64decode(cleaned, validate=False)
    except Exception as exc:
        log.error(
            "Failed to decode DOUYIN_COOKIES_B64 (len=%d): %s",
            len(cleaned),
            exc,
        )
        return None

    # yt-dlp đọc cookie file giả định encoding là UTF-8 của hệ điều hành.
    # Cookie extension trên Windows hay export thành cp1252 / latin-1.
    # Decode với fallback chain rồi re-encode về UTF-8 để yt-dlp đọc được.
    text: str | None = None
    used_encoding: str | None = None
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            text = decoded_bytes.decode(encoding)
            used_encoding = encoding
            break
        except UnicodeDecodeError:
            continue

    if text is None:
        log.error("Could not decode cookie bytes with any encoding")
        return None

    if used_encoding != "utf-8":
        log.info("Cookie source encoding was %s, converted to UTF-8", used_encoding)

    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
    Path(target_path).write_text(text, encoding="utf-8")
    os.chmod(target_path, 0o600)
    log.info(
        "Wrote Douyin cookies to %s (%d bytes UTF-8)",
        target_path,
        len(text.encode("utf-8")),
    )
    _check_cookie_freshness(text)
    return target_path
