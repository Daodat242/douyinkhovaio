"""Video downloader với multi-provider fallback chain.

Provider 1: api.douyin.wtf (Evil0ctal/Douyin_TikTok_Download_API) — chuyên
            cho Douyin/TikTok, code mature. Có thể self-host qua
            DOUYIN_WTF_ENDPOINT để bỏ rate limit demo.
Provider 2: tikwm.com — free, không cần auth. Backup khi douyin.wtf down.

Mỗi provider được thử tuần tự với nhiều URL variants (chỉ cho Douyin).
First success = trả về luôn. Tất cả fail = raise error cuối cùng.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)


class DownloadError(Exception):
    pass


class TooLargeError(DownloadError):
    def __init__(self, size_mb: float, limit_mb: int):
        super().__init__(f"File {size_mb:.1f}MB exceeds limit {limit_mb}MB")
        self.size_mb = size_mb
        self.limit_mb = limit_mb


@dataclass
class VideoInfo:
    url: str
    title: str
    uploader: str
    duration: int
    filesize_mb: float | None
    thumbnail: str | None


@dataclass
class DownloadResult:
    filepath: Path
    info: VideoInfo


@dataclass
class _VideoMeta:
    """Internal: metadata từ provider, normalize trước khi tải."""
    video_url: str
    title: str
    uploader: str
    duration: int
    filesize_bytes: int | None
    thumbnail: str | None
    video_id: str


# Default = demo của Evil0ctal. Self-host: set DOUYIN_WTF_ENDPOINT=http://my-host
_DOUYIN_WTF_BASE = os.getenv("DOUYIN_WTF_ENDPOINT", "https://api.douyin.wtf").rstrip("/")
_TIKWM_ENDPOINT = "https://www.tikwm.com/api/"

_REQUEST_TIMEOUT = 30
_DOWNLOAD_TIMEOUT = 120
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/139.0.0.0 Safari/537.36"
)


def _build_opener(proxy_url: str | None) -> urllib.request.OpenerDirector:
    handlers: list = []
    if proxy_url:
        handlers.append(
            urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        )
    return urllib.request.build_opener(*handlers)


def _http_get_json(full_url: str, proxy_url: str | None) -> dict:
    req = urllib.request.Request(
        full_url,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
    )
    opener = _build_opener(proxy_url)
    try:
        with opener.open(req, timeout=_REQUEST_TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise DownloadError(f"HTTP {exc.code}: {exc.reason}") from exc
    except Exception as exc:
        raise DownloadError(f"request failed: {exc}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise DownloadError(f"non-JSON response: {body[:200]}") from exc


def _fetch_via_douyin_wtf(url: str, proxy_url: str | None) -> _VideoMeta:
    full_url = (
        f"{_DOUYIN_WTF_BASE}/api/hybrid/video_data?"
        + urllib.parse.urlencode({"url": url, "minimal": "false"})
    )
    payload = _http_get_json(full_url, proxy_url)

    code = payload.get("code")
    if code != 200:
        msg = payload.get("message") or payload.get("msg") or f"code={code}"
        raise DownloadError(f"douyin.wtf: {msg}")

    data = payload.get("data") or {}
    if data.get("type") != "video":
        raise DownloadError(
            f"douyin.wtf: chỉ hỗ trợ video, type={data.get('type')}"
        )

    video_data = data.get("video_data") or {}
    video_url = video_data.get("nwm_video_url_HQ") or video_data.get("nwm_video_url")
    if not video_url:
        raise DownloadError("douyin.wtf: response không có nwm_video_url")

    author = data.get("author") or {}
    cover_data = data.get("cover_data") or {}

    return _VideoMeta(
        video_url=video_url,
        title=(data.get("desc") or "video").strip()[:200],
        uploader=(
            author.get("nickname") or author.get("unique_id") or "unknown"
        ),
        duration=int(data.get("duration") or 0),
        filesize_bytes=None,  # douyin.wtf không trả size đáng tin
        thumbnail=cover_data.get("origin_cover") or cover_data.get("cover"),
        video_id=str(data.get("video_id") or ""),
    )


def _is_rate_limit_message(msg: str) -> bool:
    msg_lower = msg.lower()
    return any(kw in msg_lower for kw in ("rate limit", "limit", "free api", "too many"))


def _fetch_via_tikwm(url: str, proxy_url: str | None) -> _VideoMeta:
    last_msg = ""
    for attempt in range(3):
        if attempt > 0:
            time.sleep(1.5)
        full_url = (
            _TIKWM_ENDPOINT
            + "?"
            + urllib.parse.urlencode({"url": url, "hd": "1"})
        )
        try:
            payload = _http_get_json(full_url, proxy_url)
        except DownloadError as exc:
            if "429" in str(exc) and attempt < 2:
                last_msg = "HTTP 429"
                continue
            raise

        if payload.get("code") == 0:
            data = payload.get("data")
            if not isinstance(data, dict):
                raise DownloadError("tikwm response missing 'data'")
            video_url = data.get("hdplay") or data.get("play")
            if not video_url:
                raise DownloadError("tikwm: response không có video URL")
            author = data.get("author") or {}
            return _VideoMeta(
                video_url=video_url,
                title=(data.get("title") or "video").strip()[:200],
                uploader=(
                    author.get("nickname") or author.get("unique_id") or "unknown"
                ),
                duration=int(data.get("duration") or 0),
                filesize_bytes=data.get("hd_size") or data.get("size"),
                thumbnail=data.get("cover") or data.get("origin_cover"),
                video_id=str(data.get("id") or ""),
            )

        msg = payload.get("msg") or "unknown tikwm error"
        log.warning("tikwm error msg=%r url=%s", msg, url)
        if _is_rate_limit_message(msg) and attempt < 2:
            last_msg = msg
            continue
        raise DownloadError(f"tikwm: {msg}")

    raise DownloadError(f"tikwm: rate limited sau 3 lần thử ({last_msg})")


_PROVIDERS: list[tuple[str, Callable[[str, str | None], _VideoMeta]]] = [
    ("douyin.wtf", _fetch_via_douyin_wtf),
    ("tikwm.com", _fetch_via_tikwm),
]

_DOUYIN_HOST_RE = re.compile(
    r"^https?://(?:www\.)?(?:douyin\.com|iesdouyin\.com)/", re.IGNORECASE
)
_DOUYIN_ID_RE = re.compile(r"/(?:share/)?(?:video|note)/(\d+)", re.IGNORECASE)


def _generate_url_variants(url: str) -> list[str]:
    """Tạo URL variants cho Douyin (TikTok và short link không cần)."""
    variants = [url]
    if not _DOUYIN_HOST_RE.match(url):
        return variants
    m = _DOUYIN_ID_RE.search(url)
    if not m:
        return variants
    video_id = m.group(1)
    for alt in (
        f"https://www.iesdouyin.com/share/video/{video_id}/",
        f"https://www.douyin.com/video/{video_id}",
        f"https://www.douyin.com/share/video/{video_id}",
    ):
        if alt != url and alt not in variants:
            variants.append(alt)
    return variants


def _is_url_format_error(exc: DownloadError) -> bool:
    """Lỗi do URL format không hợp lệ → đáng thử variant khác."""
    err = str(exc).lower()
    return any(
        kw in err for kw in ("url parsing", "not found", "invalid url", "404")
    )


def _fetch_meta(url: str, proxy_url: str | None) -> _VideoMeta:
    """Thử [provider × URL variant] tuần tự, trả về first success.

    Strategy: với mỗi provider, thử tất cả variants. Nếu provider chết
    hoàn toàn (network/HTTP error), skip sang provider tiếp theo. Chỉ
    raise nếu tất cả providers × variants đều fail.
    """
    variants = _generate_url_variants(url)
    last_exc: DownloadError | None = None

    for provider_name, fetcher in _PROVIDERS:
        for variant in variants:
            try:
                meta = fetcher(variant, proxy_url)
                log.info(
                    "Provider=%s thành công (URL=%s, video_id=%s)",
                    provider_name,
                    variant,
                    meta.video_id,
                )
                return meta
            except DownloadError as exc:
                last_exc = exc
                if _is_url_format_error(exc):
                    log.info(
                        "Provider=%s reject URL=%s (%s) — thử variant tiếp",
                        provider_name,
                        variant,
                        exc,
                    )
                    continue
                # Provider down hẳn → bỏ qua các variant còn lại
                log.warning(
                    "Provider=%s lỗi không phải URL format: %s — skip provider",
                    provider_name,
                    exc,
                )
                break

    assert last_exc is not None, "_PROVIDERS không thể rỗng"
    raise last_exc


def _http_download(video_url: str, dest: Path, proxy_url: str | None) -> None:
    req = urllib.request.Request(
        video_url,
        headers={
            "User-Agent": _USER_AGENT,
            # Douyin CDN đôi khi check Referer.
            "Referer": "https://www.douyin.com/",
        },
    )
    opener = _build_opener(proxy_url)
    try:
        with opener.open(req, timeout=_DOWNLOAD_TIMEOUT) as resp:
            with dest.open("wb") as f:
                shutil.copyfileobj(resp, f, length=64 * 1024)
    except Exception as exc:
        raise DownloadError(f"video download failed: {exc}") from exc


def _download_sync(
    url: str,
    download_dir: Path,
    max_filesize_mb: int,
    proxy_url: str | None,
) -> DownloadResult:
    meta = _fetch_meta(url, proxy_url)

    if meta.filesize_bytes:
        declared_mb = meta.filesize_bytes / 1024 / 1024
        if declared_mb > max_filesize_mb:
            raise TooLargeError(declared_mb, max_filesize_mb)

    job_id = uuid.uuid4().hex[:12]
    job_dir = download_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    video_id = meta.video_id or job_id
    filepath = job_dir / f"{video_id}.mp4"

    try:
        _http_download(meta.video_url, filepath, proxy_url)
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise

    size_mb = filepath.stat().st_size / 1024 / 1024
    if size_mb > max_filesize_mb:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise TooLargeError(size_mb, max_filesize_mb)

    info = VideoInfo(
        url=url,
        title=meta.title,
        uploader=meta.uploader,
        duration=meta.duration,
        filesize_mb=size_mb,
        thumbnail=meta.thumbnail,
    )
    return DownloadResult(filepath=filepath, info=info)


async def download(
    url: str,
    download_dir: Path,
    max_filesize_mb: int,
    proxy_url: str | None = None,
) -> DownloadResult:
    return await asyncio.to_thread(
        _download_sync, url, download_dir, max_filesize_mb, proxy_url
    )


def cleanup_file(path: Path) -> None:
    try:
        if path.exists():
            shutil.rmtree(path.parent, ignore_errors=True)
    except Exception as exc:
        log.warning("Cleanup failed for %s: %s", path, exc)
