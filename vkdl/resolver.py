"""Album source dispatch.

A *source* is a callable ``(album_url, session, cfg) -> AlbumResult | None``:

* returns ``(photos, title)`` on success;
* returns ``None`` to pass — "I have no result, try the next source";
* may raise ``requests.RequestException`` for a real failure, which propagates
  to the caller instead of being swallowed.

``resolve_album`` walks a chain of sources and returns the first non-``None``
result. The chain is built by :func:`default_sources` from the optional token.
"""
from .api_client import fetch_album
from .scraper import scrape_album
from .config import DownloadConfig

# (photos, title)
AlbumResult = tuple


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


def resolve_album(album_url, session, cfg: DownloadConfig, token=None,
                  sources=None):
    sources = sources if sources is not None else default_sources(token)
    for source in sources:
        result = source(album_url, session, cfg)
        if result is not None:
            return result
    return [], "VK_Album"
