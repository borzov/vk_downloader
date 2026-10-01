import json

import requests
import responses

from vkdl.config import DownloadConfig
from vkdl.scraper import parse_photos, parse_album_meta, extract_ajax_html, scrape_album

ROW = (
    '<div class="photos_row" data-id="-1_99" '
    'style="background-image:url(https://s/p.jpg?as=100x75,800x600&cs=100x0)"></div>'
)
PAGE = (
    '<div class="photos_album_intro"><h1>My Album</h1></div>'
    '<div class="ui_crumb_count">155</div>' + ROW
)
PAGE_TOTAL_2 = (
    '<div class="photos_album_intro"><h1>Two</h1></div>'
    '<div class="ui_crumb_count">2</div>' + ROW
)
AJAX_ROW = (
    '<div class="photos_row" data-id="-1_100" '
    'style="background-image:url(https://s/q.jpg?as=100x75,800x600&cs=100x0)"></div>'
)
AJAX_PAGE = json.dumps({"payload": [0, [80, AJAX_ROW]]})


def test_parse_photos_extracts_id_and_urls():
    photos = parse_photos(PAGE)
    assert len(photos) == 1
    assert photos[0].id == "-1_99"
    assert any("800" in u for u in photos[0].urls)


def test_parse_album_meta():
    title, count = parse_album_meta(PAGE)
    assert title == "My Album"
    assert count == 155


def test_parse_album_meta_defaults_when_missing():
    title, count = parse_album_meta("<div></div>")
    assert title == "VK_Album"
    assert count == 0


def test_extract_ajax_html_finds_fragment():
    payload = {"payload": [0, [80, '<div class="photos_row" data-id="1_2"></div>']]}
    html = extract_ajax_html(json.dumps(payload))
    assert html is not None and "photos_row" in html


def test_extract_ajax_html_bad_json_returns_none():
    assert extract_ajax_html("not json") is None


@responses.activate
def test_scrape_album_survives_transient_ajax_failure():
    """Pagination rides the network seam: a dropped AJAX page is retried,
    not fatal for the whole album."""
    url = "https://vk.com/album-1_2"
    responses.add(responses.GET, url, body=PAGE_TOTAL_2, status=200)
    responses.add(responses.POST, url,
                  body=requests.exceptions.ConnectionError("drop"))
    responses.add(responses.POST, url, body=AJAX_PAGE, status=200)
    cfg = DownloadConfig(retries=2, backoff_base=0, rate_limit_delay=0)
    photos, title = scrape_album(url, requests.Session(), cfg)
    assert title == "Two"
    assert [p.id for p in photos] == ["-1_99", "-1_100"]
