import json
from vkdl.scraper import parse_photos, parse_album_meta, extract_ajax_html

ROW = (
    '<div class="photos_row" data-id="-1_99" '
    'style="background-image:url(https://s/p.jpg?as=100x75,800x600&cs=100x0)"></div>'
)
PAGE = (
    '<div class="photos_album_intro"><h1>My Album</h1></div>'
    '<div class="ui_crumb_count">155</div>' + ROW
)


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
