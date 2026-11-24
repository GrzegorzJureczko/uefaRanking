import requests
from requests.adapters import HTTPAdapter

# One pooled session reuses TCP/TLS connections; the pool is sized for the parallel per-league requests
POOL_SIZE = 32

session = requests.Session()
for prefix in ("https://", "http://"):
    session.mount(prefix, HTTPAdapter(pool_connections=POOL_SIZE, pool_maxsize=POOL_SIZE))
