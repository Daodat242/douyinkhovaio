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


def _canonicalize(url: str, kind: UrlKind) -> str:
    """yt-dlp không nhận URL dạng douyin.com/jingxuan?modal_id=ID — rewrite
    về douyin.com/video/ID để extractor xử lý được."""
    if kind == UrlKind.DOUYIN_VIDEO:
        m = _MODAL_ID_RE.match(url)
        if m:
            return f"https://www.douyin.com/video/{m.group(1)}"
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
