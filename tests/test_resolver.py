from vkdl.resolver import resolve_album
from vkdl.scraper import Photo
from vkdl.config import DownloadConfig

def _scrape_stub(url, session, cfg):
    return [Photo(id="s_1", urls=["scraped"])], "ScrapeTitle"

def test_uses_scraper_when_no_token():
    photos, title = resolve_album("u", None, DownloadConfig(), token=None,
                                  api_fn=lambda *a, **k: None, scrape_fn=_scrape_stub)
    assert title == "ScrapeTitle"
    assert photos[0].id == "s_1"

def test_uses_api_when_token_and_success():
    def api_ok(url, token, session, cfg):
        return [Photo(id="a_1", urls=["api"])], "ApiTitle"
    photos, title = resolve_album("u", None, DownloadConfig(), token="tok",
                                  api_fn=api_ok, scrape_fn=_scrape_stub)
    assert title == "ApiTitle"

def test_falls_back_to_scraper_when_api_returns_none():
    photos, title = resolve_album("u", None, DownloadConfig(), token="tok",
                                  api_fn=lambda *a, **k: None, scrape_fn=_scrape_stub)
    assert title == "ScrapeTitle"
