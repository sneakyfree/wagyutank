"""In-process sliding-window rate limiter (per API worker).

Good enough to blunt brute-force and email-bombing at this stage; swap for a
Redis-backed limiter when the API scales past one box."""
import threading
import time

_hits: dict[str, list[float]] = {}
_lock = threading.Lock()


def allow(key: str, limit: int, window_s: float) -> bool:
    """Record a hit for `key`; return False if it exceeds `limit` in `window_s`."""
    now = time.monotonic()
    with _lock:
        bucket = [t for t in _hits.get(key, []) if now - t < window_s]
        if len(bucket) >= limit:
            _hits[key] = bucket
            return False
        bucket.append(now)
        _hits[key] = bucket
        # opportunistic cleanup so the dict doesn't grow unbounded
        if len(_hits) > 5000:
            for k in [k for k, v in _hits.items() if not v or now - v[-1] > window_s]:
                _hits.pop(k, None)
        return True
