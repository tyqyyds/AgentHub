"""
Simple in-memory cache with TTL for API responses.
Reduces repeated database queries for low-frequency-change data.
"""

import time
import threading
from typing import Any, Optional, Callable
from functools import wraps
import logging

logger = logging.getLogger(__name__)


class SimpleCache:
    """Thread-safe in-memory cache with TTL support."""

    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._store:
                value, expires_at = self._store[key]
                if time.time() < expires_at:
                    return value
                del self._store[key]
        return None

    def set(self, key: str, value: Any, ttl_seconds: int = 60):
        with self._lock:
            self._store[key] = (value, time.time() + ttl_seconds)

    def invalidate(self, key: str):
        with self._lock:
            self._store.pop(key, None)

    def invalidate_pattern(self, prefix: str):
        with self._lock:
            keys_to_delete = [k for k in self._store if k.startswith(prefix)]
            for k in keys_to_delete:
                del self._store[k]

    def clear(self):
        with self._lock:
            self._store.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)


# Global cache instance
api_cache = SimpleCache()


def cached(ttl_seconds: int = 60, key_prefix: str = ""):
    """Decorator for caching async function results.

    Usage:
        @cached(ttl_seconds=60, key_prefix="sla_dashboard")
        async def get_sla_dashboard():
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Build cache key from function name + args
            cache_key = f"{key_prefix or func.__name__}:{hash(str(args) + str(kwargs))}"

            # Try cache first
            cached_result = api_cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit: {cache_key}")
                return cached_result

            # Execute function
            result = await func(*args, **kwargs)

            # Store in cache
            api_cache.set(cache_key, result, ttl_seconds)
            logger.debug(f"Cache miss: {cache_key}, stored for {ttl_seconds}s")

            return result
        return wrapper
    return decorator
