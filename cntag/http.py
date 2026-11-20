"""Shared requests.Session so catalog requests reuse TLS connections."""
from __future__ import annotations

import threading

import requests
from requests.adapters import HTTPAdapter

_session: requests.Session | None = None
_session_lock = threading.Lock()


def http_session() -> requests.Session:
    """urllib3 pools are thread-safe; one session for the whole app."""
    global _session
    with _session_lock:
        if _session is None:
            session = requests.Session()
            adapter = HTTPAdapter(pool_connections=8, pool_maxsize=16)
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            _session = session
        return _session
