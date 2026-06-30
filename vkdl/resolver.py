"""Hybrid source dispatch: optional API first (token-only), scraper fallback."""
from .api_client import fetch_album as _default_api
from .scraper import scrape_album as _default_scrape
from .config import DownloadConfig


def resolve_album(album_url, session, cfg: DownloadConfig, token=None,
                  api_fn=_default_api, scrape_fn=_default_scrape):
    if token:
        result = api_fn(album_url, token, session, cfg)
        if result is not None:
            return result
    return scrape_fn(album_url, session, cfg)
