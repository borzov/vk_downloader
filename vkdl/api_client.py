"""OPTIONAL VK API path. Used only when a token is present; None when it passes."""
import requests
from .models import Album, Photo
from .album_ref import parse as parse_album_ref
from .config import DownloadConfig
from .http import get as http_get

API_VERSION = "5.199"


def photos_to_models(api_json: dict) -> list:
    items = api_json.get("response", {}).get("items", [])
    photos = []
    for it in items:
        sizes = sorted(it.get("sizes", []), key=lambda s: s.get("width", 0), reverse=True)
        urls = [s["url"] for s in sizes if s.get("url")]
        if urls:
            photos.append(Photo(id=f"{it.get('owner_id')}_{it.get('id')}", urls=urls))
    return photos


def fetch_album(album_url: str, token: str, session, cfg: DownloadConfig = DownloadConfig()):
    """Optional API source. Returns an :class:`Album` or ``None`` to pass.

    ``None`` means "API unavailable/unusable, fall back to the next source".
    Only *expected* failures (URL shape, network, malformed API response) map to
    ``None``; unexpected errors are left to propagate so bugs are not masked.
    """
    ref = parse_album_ref(album_url)
    if ref is None:
        return None
    owner, album = ref.owner_id, ref.album_id
    try:
        r = http_get(session, "https://api.vk.com/method/photos.get", cfg,
                     params={
                         "owner_id": owner, "album_id": album, "count": 1000,
                         "photo_sizes": 1, "access_token": token,
                         "v": API_VERSION,
                     }, headers={"Accept": "application/json"})
        data = r.json()
    except (requests.RequestException, ValueError):
        return None
    if "error" in data:
        return None
    photos = photos_to_models(data)
    if not photos:
        return None
    return Album(photos=photos, title=f"album{owner}_{album}", source="api")
