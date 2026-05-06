import hashlib
import json
import logging
from dataclasses import asdict, dataclass

import redis.asyncio as redis

log = logging.getLogger(__name__)


@dataclass
class CachedFile:
    file_id: str
    title: str
    uploader: str


def _key(url: str) -> str:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    return f"vidcache:{digest}"


class FileCache:
    def __init__(self, client: redis.Redis, ttl: int):
        self._r = client
        self._ttl = ttl

    async def get(self, url: str) -> CachedFile | None:
        raw = await self._r.get(_key(url))
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return CachedFile(**data)
        except Exception as exc:
            log.warning("Corrupt cache entry for %s: %s", url, exc)
            return None

    async def set(self, url: str, cached: CachedFile) -> None:
        await self._r.set(_key(url), json.dumps(asdict(cached)), ex=self._ttl)
