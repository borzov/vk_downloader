"""The network seam: session factory + retrying GET/POST.

Every request the package makes goes through here — one User-Agent, one
retry/backoff policy, one timeout knob. A 404 is returned to the caller
without retries (callers treat it as data, not failure); anything else that
raises is retried with exponential backoff.
"""
import time

import requests

from .config import HEADERS


def make_session() -> requests.Session:
    """Session with the common headers installed."""
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def _request(session, method, url, cfg, **kwargs):
    kwargs.setdefault("timeout", cfg.request_timeout)
    last = None
    for attempt in range(cfg.retries):
        try:
            r = session.request(method, url, **kwargs)
            if r.status_code == 404:
                return r
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            time.sleep(cfg.backoff_base * (2 ** attempt))
    raise last if last else requests.RequestException("unknown")


def get(session, url, cfg, **kwargs):
    return _request(session, "GET", url, cfg, **kwargs)


def post(session, url, cfg, **kwargs):
    return _request(session, "POST", url, cfg, **kwargs)
