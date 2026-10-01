import pytest
import requests

from vkdl.config import DownloadConfig
from vkdl.models import Album, Photo
from vkdl.resolver import default_sources, resolve_album


def _scraper_stub(url, session, cfg):
    return Album(photos=[Photo(id="s_1", urls=["scraped"])],
                 title="ScrapeTitle", source="scraper")


def test_returns_album_from_the_source_that_produced_it():
    album = resolve_album("u", None, DownloadConfig(), sources=[_scraper_stub])
    assert album.title == "ScrapeTitle"
    assert album.source == "scraper"
    assert album.photos[0].id == "s_1"


def test_first_passing_source_is_skipped():
    def api_ok(url, session, cfg):
        return Album(photos=[Photo(id="a_1", urls=["api"])],
                     title="ApiTitle", source="api")

    album = resolve_album("u", None, DownloadConfig(),
                          sources=[lambda *a: None, api_ok])
    assert album.title == "ApiTitle"


def test_exhausted_chain_returns_none():
    result = resolve_album("u", None, DownloadConfig(),
                           sources=[lambda *a: None])
    assert result is None


def test_network_error_propagates_not_swallowed():
    def boom(url, session, cfg):
        raise requests.RequestException("down")

    with pytest.raises(requests.RequestException):
        resolve_album("u", None, DownloadConfig(), sources=[boom])


def test_default_sources_scraper_only_without_token():
    assert len(default_sources(None)) == 1


def test_default_sources_api_then_scraper_with_token():
    assert len(default_sources("tok")) == 2
