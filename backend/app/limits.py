import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import HTTPException, Request


class RateLimiter:
    """Sliding-window limiter, per client, kept in memory (resets on restart)."""

    def __init__(self, max_calls: int, window_seconds: int):
        self.max_calls = max_calls
        self.window = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.max_calls:
                retry_after = max(1, int(self.window - (now - hits[0])))
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please wait a moment and try again.",
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)
            if len(self._hits) > 5000:
                for k in [k for k, v in self._hits.items() if not v]:
                    del self._hits[k]

    def blocked(self, key: str) -> bool:
        """True while this client has used up its allowance (looks without counting a new hit)."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            return len(hits) >= self.max_calls

    def record(self, key: str) -> None:
        with self._lock:
            self._hits[key].append(time.monotonic())


def client_key(request: Request) -> str:
    # Railway's proxy appends the real client address to X-Forwarded-For, so the rightmost
    # entry is the one we can trust; earlier entries can be forged by the caller.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


_verify_limiter = RateLimiter(max_calls=20, window_seconds=60)
_report_limiter = RateLimiter(max_calls=10, window_seconds=60)


_feedback_limiter = RateLimiter(max_calls=3, window_seconds=600)
# Only wrong admin keys count: five misses in ten minutes lock that visitor out for ten minutes,
# and while locked even the right key is refused, so guessing gains nothing.
_admin_fail_limiter = RateLimiter(max_calls=5, window_seconds=600)


def admin_locked(request: Request) -> None:
    if _admin_fail_limiter.blocked(client_key(request)):
        raise HTTPException(status_code=429, detail="Too many wrong keys. Try again in about ten minutes.")


def admin_key_failed(request: Request) -> None:
    _admin_fail_limiter.record(client_key(request))


def limit_feedback(request: Request) -> None:
    _feedback_limiter.check(client_key(request))


def limit_verify(request: Request) -> None:
    _verify_limiter.check(client_key(request))


def limit_report(request: Request) -> None:
    _report_limiter.check(client_key(request))


_llm_lock = threading.Lock()
_llm_day = ""
_llm_calls = 0


def consume_llm_call() -> bool:
    """Count one paid AI call against today's ceiling. False once the ceiling is reached."""
    global _llm_day, _llm_calls
    cap = int(os.getenv("LLM_DAILY_CAP", "1000"))
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _llm_lock:
        if today != _llm_day:
            _llm_day, _llm_calls = today, 0
        if _llm_calls >= cap:
            return False
        _llm_calls += 1
        return True
