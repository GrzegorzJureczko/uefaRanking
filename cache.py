import json
import os
import time

# Simple file-based cache for API responses

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'data')
CACHE_FILE = os.path.join(CACHE_DIR, 'cache.json')

def _ensure_cache_file():
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR, exist_ok=True)
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f)

def _read_cache():
    try:
        _ensure_cache_file()
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def _write_cache(data):
    try:
        _ensure_cache_file()
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except Exception:
        pass

def get_cache(key, ttl_seconds=86400):
    """Return cached value for key if not older than ttl_seconds, else None."""
    cache = _read_cache()
    entry = cache.get(key)
    if not entry:
        return None
    ts = entry.get('ts', 0)
    if time.time() - ts > ttl_seconds:
        return None
    return entry.get('data')

def set_cache(key, data):
    """Store data under key with current timestamp."""
    cache = _read_cache()
    cache[key] = {
        'ts': int(time.time()),
        'data': data
    }
    _write_cache(cache)

def clear_cache(key=None):
    """Clear a specific cache key or the whole cache if key is None."""
    cache = _read_cache()
    if key is None:
        cache = {}
    else:
        cache.pop(key, None)
    _write_cache(cache)
