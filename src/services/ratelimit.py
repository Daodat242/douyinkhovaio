from dataclasses import dataclass

import redis.asyncio as redis


@dataclass
class RateLimitResult:
    allowed: bool
    used: int
    limit: int
    retry_after: int


class RateLimiter:
    def __init__(self, client: redis.Redis, limit: int, window_seconds: int):
        self._r = client
        self._limit = limit
        self._window = window_seconds

    def _key(self, user_id: int) -> str:
        return f"ratelimit:{user_id}"

    async def hit(self, user_id: int) -> RateLimitResult:
        key = self._key(user_id)
        pipe = self._r.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        used, ttl = await pipe.execute()

        if ttl < 0:
            await self._r.expire(key, self._window)
            ttl = self._window

        if used > self._limit:
            return RateLimitResult(False, used, self._limit, max(ttl, 1))
        return RateLimitResult(True, used, self._limit, ttl)
