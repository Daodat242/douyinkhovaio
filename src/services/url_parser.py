import re
from dataclasses import dataclass
from enum import Enum


class UrlKind(str, Enum):
    DOUYIN_VIDEO = "douyin_video"
    DOUYIN_USER = "douyin_user"
    TIKTOK_VIDEO = "tiktok_video"
    TIKTOK_USER = "tiktok_user"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ParsedUrl:
    raw: str
    kind: UrlKind
    canonical: str

    @property
    def is_video(self) -> bool:
        return self.kind in (UrlKind.DOUYIN_VIDEO, UrlKind.TIKTOK_VIDEO)

    @property
    def is_user(self) -> bool:
        return self.kind in (UrlKind.DOUYIN_USER, UrlKind.TIKTOK_USER)

    @property
    def is_supported(self) -> bool:
        return self.kind != UrlKind.UNKNOWN


_URL_RE = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)

_MODAL_ID_RE = re.compile(
    r"^https?://(?:www\.)?douyin\.com/[\w-]*\?[^#]*\bmodal_id=(\d+)",
    re.IGNORECASE,
)

# Regex để extract video ID từ các URL douyin.com/<path>/<id>.
_DOUYIN_VIDEO_ID_RE = re.compile(
    r"^https?://(?:www\.)?douyin\.com/(?:video|share/video|note)/(\d+)",
    re.IGNORECASE,
)
_IESDOUYIN_VIDEO_ID_RE = re.compile(
    r"^https?://(?:www\.)?iesdouyin\.com/share/(?:video|note)/(\d+)",
    re.IGNORECASE,
)

_PATTERNS: list[tuple[re.Pattern[str], UrlKind]] = [
    (re.compile(r"^https?://v\.douyin\.com/[\w-]+/?", re.IGNORECASE), UrlKind.DOUYIN_VIDEO),
    (
        re.compile(r"^https?://(?:www\.)?douyin\.com/(?:video|share/video|note)/\d+", re.IGNORECASE),
        UrlKind.DOUYIN_VIDEO,
    ),
    (_MODAL_ID_RE, UrlKind.DOUYIN_VIDEO),
    (
        re.compile(r"^https?://(?:www\.)?iesdouyin\.com/share/(?:video|note)/\d+", re.IGNORECASE),
        UrlKind.DOUYIN_VIDEO,
    ),
    (
        re.compile(r"^https?://(?:www\.)?douyin\.com/user/[\w-]+", re.IGNORECASE),
        UrlKind.DOUYIN_USER,
    ),
    (
        re.compile(r"^https?://(?:vm|vt)\.tiktok\.com/[\w-]+/?", re.IGNORECASE),
        UrlKind.TIKTOK_VIDEO,
    ),
    (
        re.compile(
            r"^https?://(?:www\.)?tiktok\.com/(?:@[\w.-]+/video/\d+|t/[\w-]+|v/\d+)",
            re.IGNORECASE,
        ),
        UrlKind.TIKTOK_VIDEO,
    ),
    (
        re.compile(r"^https?://(?:www\.)?tiktok\.com/@[\w.-]+/?$", re.IGNORECASE),
        UrlKind.TIKTOK_USER,
    ),
]


def _extract_douyin_video_id(url: str) -> str | None:
    for pattern in (_DOUYIN_VIDEO_ID_RE, _IESDOUYIN_VIDEO_ID_RE, _MODAL_ID_RE):
        m = pattern.match(url)
        if m:
            return m.group(1)
    return None


def _canonicalize(url: str, kind: UrlKind) -> str:
    """Rewrite về dạng iesdouyin.com/share/video/<id>/ — đây là URL share
    chuẩn của Douyin, được tikwm.com cùng nhiều downloader khác support
    rộng rãi hơn so với douyin.com/video/<id>."""
    if kind == UrlKind.DOUYIN_VIDEO:
        video_id = _extract_douyin_video_id(url)
        if video_id:
            return f"https://www.iesdouyin.com/share/video/{video_id}/"
    return url


def extract_first_url(text: str) -> str | None:
    match = _URL_RE.search(text)
    return match.group(0) if match else None


def parse(url: str) -> ParsedUrl:
    cleaned = url.strip()
    for pattern, kind in _PATTERNS:
        if pattern.match(cleaned):
            return ParsedUrl(raw=cleaned, kind=kind, canonical=_canonicalize(cleaned, kind))
    return ParsedUrl(raw=cleaned, kind=UrlKind.UNKNOWN, canonical=cleaned)


def parse_message(text: str) -> ParsedUrl | None:
    url = extract_first_url(text)
    if not url:
        return None
    return parse(url)
