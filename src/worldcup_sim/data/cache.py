"""In-memory TTL cache for data fetching functions."""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


class TTLCache:
    """In-memory cache with time-to-live expiry.

    Usage as a decorator::

        @TTLCache(ttl_seconds=30)
        def expensive_function():
            ...

    The cached value is shared across all calls while it remains fresh.
    """

    _cached_value: Any = None
    _cached_at: float = 0.0
    _lock: bool = False

    def __init__(self, ttl_seconds: float = 30) -> None:
        self._ttl = ttl_seconds

    def __call__(self, func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            now = time.monotonic()
            if (
                self._cached_at > 0
                and (now - self._cached_at) < self._ttl
                and self._cached_value is not None
            ):
                return self._cached_value
            self._cached_value = func(*args, **kwargs)
            self._cached_at = now
            return self._cached_value

        return wrapper  # type: ignore[return-value]

    def clear(self) -> None:
        """Manually invalidate the cache."""
        self._cached_value = None
        self._cached_at = 0.0

    def is_fresh(self) -> bool:
        """Check if the cached value is still valid."""
        if self._cached_at == 0.0:
            return False
        return (time.monotonic() - self._cached_at) < self._ttl
