import base64
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)


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

    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
    Path(target_path).write_bytes(decoded_bytes)
    os.chmod(target_path, 0o600)
    log.info("Wrote Douyin cookies to %s (%d bytes)", target_path, len(decoded_bytes))
    return target_path
