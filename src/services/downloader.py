import asyncio
import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

log = logging.getLogger(__name__)

try:
    from yt_dlp.networking.impersonate import ImpersonateTarget

    _IMPERSONATE_TARGET: object | None = ImpersonateTarget.from_str("chrome")
except Exception as _impersonate_exc:
    log.warning(
        "yt-dlp impersonate target unavailable (%s) — TLS fingerprint sẽ là default",
        _impersonate_exc,
    )
    _IMPERSONATE_TARGET = None

# Được đặt thành False khi runtime phát hiện curl_cffi không hỗ trợ target.
_impersonate_enabled = _IMPERSONATE_TARGET is not None


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


_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.douyin.com/",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# iesdouyin.com là API legacy, anti-bot lỏng hơn so với www.douyin.com.
_DOUYIN_EXTRACTOR_ARGS = {
    "douyin": {"api_hostname": ["www.iesdouyin.com"]},
}


def _base_opts(cookies_path: str | None, *, impersonate: bool = True) -> dict:
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "http_headers": _DEFAULT_HEADERS,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        "extractor_args": _DOUYIN_EXTRACTOR_ARGS,
    }
    if impersonate and _impersonate_enabled and _IMPERSONATE_TARGET is not None:
        opts["impersonate"] = _IMPERSONATE_TARGET
    if cookies_path and os.path.exists(cookies_path):
        opts["cookiefile"] = cookies_path
    return opts


def _probe(url: str, cookies_path: str | None) -> dict:
    opts = _base_opts(cookies_path)
    opts["skip_download"] = True
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _to_video_info(url: str, info: dict) -> VideoInfo:
    filesize = info.get("filesize") or info.get("filesize_approx")
    return VideoInfo(
        url=url,
        title=(info.get("title") or "video").strip()[:200],
        uploader=info.get("uploader") or info.get("uploader_id") or "unknown",
        duration=int(info.get("duration") or 0),
        filesize_mb=(filesize / 1024 / 1024) if filesize else None,
        thumbnail=info.get("thumbnail"),
    )


async def probe(url: str, cookies_path: str | None) -> VideoInfo:
    info = await asyncio.to_thread(_probe, url, cookies_path)
    return _to_video_info(url, info)


def _run_ydl(url: str, job_dir: Path, opts: dict) -> tuple[dict, Path]:
    """Chạy yt-dlp, trả về (info, filepath). Raise nếu fail."""
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filepath = Path(ydl.prepare_filename(info))
        if not filepath.exists():
            candidates = list(job_dir.iterdir())
            if not candidates:
                raise DownloadError("yt-dlp ran but no file produced")
            filepath = max(candidates, key=lambda p: p.stat().st_size)
    return info, filepath


def _download_sync(
    url: str,
    download_dir: Path,
    cookies_path: str | None,
    max_filesize_mb: int,
) -> DownloadResult:
    global _impersonate_enabled

    job_id = uuid.uuid4().hex[:12]
    job_dir = download_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    extra = {
        "outtmpl": str(job_dir / "%(id)s.%(ext)s"),
        # Douyin thường không có filesize chính xác → dùng filesize_approx,
        # fallback "best" để không bị loại hết format.
        "format": (
            f"best[filesize_approx<?{max_filesize_mb}M]"
            f"/best[filesize<?{max_filesize_mb}M]"
            f"/best"
        ),
        "noplaylist": True,
        "merge_output_format": "mp4",
    }

    try:
        opts = _base_opts(cookies_path, impersonate=True)
        opts.update(extra)
        info, filepath = _run_ydl(url, job_dir, opts)
    except Exception as exc:
        err_str = str(exc)
        # curl_cffi không support target này trên môi trường hiện tại →
        # tắt impersonation và retry ngay, không fail toàn bộ request.
        if _impersonate_enabled and "impersonate" in err_str.lower():
            log.warning("Impersonation unavailable on this host, disabling: %s", exc)
            _impersonate_enabled = False
            try:
                opts = _base_opts(cookies_path, impersonate=False)
                opts.update(extra)
                info, filepath = _run_ydl(url, job_dir, opts)
            except yt_dlp.utils.DownloadError as exc2:
                shutil.rmtree(job_dir, ignore_errors=True)
                raise DownloadError(str(exc2)) from exc2
            except Exception:
                shutil.rmtree(job_dir, ignore_errors=True)
                raise
        elif isinstance(exc, yt_dlp.utils.DownloadError):
            shutil.rmtree(job_dir, ignore_errors=True)
            raise DownloadError(str(exc)) from exc
        else:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise

    size_mb = filepath.stat().st_size / 1024 / 1024
    if size_mb > max_filesize_mb:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise TooLargeError(size_mb, max_filesize_mb)

    video_info = _to_video_info(url, info)
    if video_info.filesize_mb is None:
        video_info = VideoInfo(**{**video_info.__dict__, "filesize_mb": size_mb})
    return DownloadResult(filepath=filepath, info=video_info)


async def download(
    url: str,
    download_dir: Path,
    cookies_path: str | None,
    max_filesize_mb: int,
) -> DownloadResult:
    return await asyncio.to_thread(
        _download_sync, url, download_dir, cookies_path, max_filesize_mb
    )


def cleanup_file(path: Path) -> None:
    try:
        if path.exists():
            shutil.rmtree(path.parent, ignore_errors=True)
    except Exception as exc:
        log.warning("Cleanup failed for %s: %s", path, exc)
