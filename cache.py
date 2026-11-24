import functools
import inspect
import threading
import time


class TTLCache:
    """Thread-safe in-memory cache whose entries expire after a per-entry time to live."""

    def __init__(self):
        self._entries = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            entry = self._entries.get(key)
            if entry and entry[0] > time.monotonic():
                return entry[1]
            self._entries.pop(key, None)
            return None

    def set(self, key, value, ttl):
        with self._lock:
            self._entries[key] = (time.monotonic() + ttl, value)

    def clear(self):
        with self._lock:
            self._entries.clear()


def ttl_cache(ttl):
    """
    Cache a function's results, keyed by its (default-normalized) arguments.
    ttl is a number of seconds or a callable receiving the same arguments as the function.
    Falsy results (None, [], {}) signal a failed fetch and are never cached.
    Returned objects are shared between callers and must not be mutated.
    """
    def decorator(func):
        cache = TTLCache()
        signature = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key, bound = make_key(*args, **kwargs)
            cached = cache.get(key)
            if cached is not None:
                return cached
            return load(key, bound)

        def make_key(*args, **kwargs):
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            return tuple(bound.arguments.items()), bound

        def load(key, bound):
            result = func(*bound.args, **bound.kwargs)
            if result:
                cache.set(key, result, ttl(*bound.args, **bound.kwargs) if callable(ttl) else ttl)
            return result

        def refresh(*args, **kwargs):
            """Fetch again, bypassing the cache; the old entry stays until a successful fetch replaces it."""
            return load(*make_key(*args, **kwargs))

        wrapper.cache = cache
        wrapper.refresh = refresh
        return wrapper

    return decorator
