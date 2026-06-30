import pytest
import requests
from vkdl.resolver import resolve_album, default_sources
from vkdl.models import Photo
from vkdl.config import DownloadConfig


def _scrape_stub(url, session, cfg):
    return [Photo(id="s_1", urls=["scraped"])], "ScrapeTitle"


def test_uses_scraper_when_no_token():
    photos, title = resolve_album("u", None, DownloadConfig(), token=None,
                                  sources=[_scrape_stub])
    assert title == "ScrapeTitle"
    assert photos[0].id == "s_1"


def test_uses_first_source_that_returns_result():
    def api_ok(url, session, cfg):
        return [Photo(id="a_1", urls=["api"])], "ApiTitle"
    photos, title = resolve_album("u", None, DownloadConfig(),
                                  sources=[api_ok, _scrape_stub])
    assert title == "ApiTitle"


def test_falls_back_to_next_source_when_first_returns_none():
    photos, title = resolve_album("u", None, DownloadConfig(),
                                  sources=[lambda *a, **k: None, _scrape_stub])
    assert title == "ScrapeTitle"


def test_network_error_propagates_not_swallowed():
    def boom(url, session, cfg):
        raise requests.RequestException("down")
    with pytest.raises(requests.RequestException):
        resolve_album("u", None, DownloadConfig(), sources=[boom])


def test_empty_chain_returns_empty_result():
    photos, title = resolve_album("u", None, DownloadConfig(),
                                  sources=[lambda *a, **k: None])
    assert photos == []


def test_default_sources_scraper_only_without_token():
    assert len(default_sources(None)) == 1


def test_default_sources_api_then_scraper_with_token():
    assert len(default_sources("tok")) == 2
