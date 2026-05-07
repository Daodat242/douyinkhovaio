"""Video downloader sử dụng tikwm.com API.

Hỗ trợ Douyin và TikTok không watermark, không cần cookies hoặc xử lý
anti-bot. Đánh đổi: phụ thuộc service bên ngoài (~1 req/s rate limit).
"""

import asyncio
import json
import logging
import shutil
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

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


def _tikwm_query(url: str, proxy_url: str | None) -> dict:
    """Gọi tikwm API, trả về dict 'data' từ response."""
    params = urllib.parse.urlencode({"url": url, "hd": "1"})
    full_url = f"{_TIKWM_ENDPOINT}?{params}"
    req = urllib.request.Request(
        full_url,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
    )
    opener = _build_opener(proxy_url)
    try:
        with opener.open(req, timeout=_REQUEST_TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
    except Exception as exc:
        raise DownloadError(f"tikwm request failed: {exc}") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise DownloadError(f"tikwm returned non-JSON: {body[:200]}") from exc

    if payload.get("code") != 0:
        msg = payload.get("msg") or "unknown tikwm error"
        # Tikwm trả về "Url parsing is failed" nếu video private/đã xoá,
        # "rate limit" nếu vượt 1 req/s.
        raise DownloadError(f"tikwm: {msg}")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise DownloadError("tikwm response missing 'data'")
    return data


def _http_download(video_url: str, dest: Path, proxy_url: str | None) -> None:
    req = urllib.request.Request(video_url, headers={"User-Agent": _USER_AGENT})
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
    info = _tikwm_query(url, proxy_url)

    # hdplay = HD không watermark, play = SD không watermark.
    video_url = info.get("hdplay") or info.get("play")
    if not video_url:
        raise DownloadError("tikwm: response không có video URL")

    declared_size_bytes = info.get("size") or info.get("hd_size")
    if declared_size_bytes:
        declared_mb = declared_size_bytes / 1024 / 1024
        if declared_mb > max_filesize_mb:
            raise TooLargeError(declared_mb, max_filesize_mb)

    job_id = uuid.uuid4().hex[:12]
    job_dir = download_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    video_id = str(info.get("id") or job_id)
    filepath = job_dir / f"{video_id}.mp4"

    try:
        _http_download(video_url, filepath, proxy_url)
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise

    size_mb = filepath.stat().st_size / 1024 / 1024
    if size_mb > max_filesize_mb:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise TooLargeError(size_mb, max_filesize_mb)

    author = info.get("author") or {}
    video_info = VideoInfo(
        url=url,
        title=(info.get("title") or "video").strip()[:200],
        uploader=(
            author.get("nickname") or author.get("unique_id") or "unknown"
        ),
        duration=int(info.get("duration") or 0),
        filesize_mb=size_mb,
        thumbnail=info.get("cover") or info.get("origin_cover"),
    )
    return DownloadResult(filepath=filepath, info=video_info)


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
