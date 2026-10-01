import json

import requests
import responses

from vkdl.api_client import fetch_album, photos_to_models
from vkdl.config import DownloadConfig

API_URL = "https://api.vk.com/method/photos.get"


def test_photos_to_models_picks_largest():
    api = {"response": {"items": [
        {"id": 1, "owner_id": -5, "sizes": [
            {"type": "m", "url": "u_m", "width": 130, "height": 100},
            {"type": "w", "url": "u_w", "width": 2560, "height": 1920},
            {"type": "x", "url": "u_x", "width": 604, "height": 453},
        ]},
    ]}}
    photos = photos_to_models(api)
    assert len(photos) == 1
    assert photos[0].urls[0] == "u_w"  # largest by width first
    assert photos[0].id == "-5_1"


def test_photos_to_models_empty():
    assert photos_to_models({"response": {"items": []}}) == []


@responses.activate
def test_fetch_album_returns_album_from_api():
    body = json.dumps({"response": {"items": [
        {"id": 2, "owner_id": -1, "sizes": [
            {"type": "w", "url": "u_w", "width": 2560, "height": 1920},
            {"type": "m", "url": "u_m", "width": 130, "height": 100},
        ]},
    ]}})
    responses.add(responses.GET, API_URL, body=body, status=200)
    album = fetch_album("https://vk.com/album-1_2", "tok", requests.Session(),
                        DownloadConfig(retries=1))
    assert album is not None
    assert album.source == "api"
    assert album.title == "album-1_2"
    assert album.photos[0].id == "-1_2"
    assert album.photos[0].urls == ["u_w", "u_m"]


@responses.activate
def test_fetch_album_retries_transient_network_failure():
    """The API source rides the network seam: transient drops are retried
    before the source passes to the next one."""
    for _ in range(2):
        responses.add(responses.GET, API_URL,
                      body=requests.exceptions.ConnectionError("down"))
    responses.add(responses.GET, API_URL,
                  body=json.dumps({"error": {"error_msg": "no access"}}),
                  status=200)
    cfg = DownloadConfig(retries=3, backoff_base=0)
    result = fetch_album("https://vk.com/album-1_2", "tok", requests.Session(),
                         cfg)
    assert result is None              # API-level error -> pass to next source
    assert len(responses.calls) == 3   # retried before giving up
