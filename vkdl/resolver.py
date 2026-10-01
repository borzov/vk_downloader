"""Album source dispatch.

A *source* is a callable ``(album_url, session, cfg) -> Album | None``:

* returns an :class:`Album` when it produced one (always with photos);
* returns ``None`` to pass — "I have no result, try the next source";
* may raise ``requests.RequestException`` for a real failure, which propagates
  to the caller instead of being swallowed.

``resolve_album`` walks the chain and returns the first ``Album``, or ``None``
when every source passed. The chain is assembled by :func:`default_sources`.
"""
from typing import Protocol

from .api_client import fetch_album
from .scraper import scrape_album
from .config import DownloadConfig
from .models import Album


class AlbumSource(Protocol):
    def __call__(self, album_url: str, session,
                 cfg: DownloadConfig) -> "Album | None": ...


def _api_source(token):
    def source(album_url, session, cfg):
        return fetch_album(album_url, token, session, cfg)
    return source


def default_sources(token=None) -> list:
    """Optional API first (token-only), scraper as the final source."""
    sources = []
    if token:
        sources.append(_api_source(token))
    sources.append(scrape_album)
    return sources


def resolve_album(album_url, session, cfg: DownloadConfig,
                  sources) -> "Album | None":
    """First source to produce an Album wins; ``None`` when all passed."""
    for source in sources:
        album = source(album_url, session, cfg)
        if album is not None:
            return album
    return None
