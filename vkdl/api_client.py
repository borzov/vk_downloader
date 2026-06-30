"""OPTIONAL VK API path. Used only when a token is present; None on any failure."""
import re
from .scraper import Photo
from .config import DownloadConfig

API_VERSION = "5.199"
_ALBUM_RE = re.compile(r"album(-?\d+)_(\d+)")


def parse_owner_album(album_url: str) -> tuple:
    m = _ALBUM_RE.search(album_url)
    if not m:
        raise ValueError(f"cannot parse album url: {album_url}")
    return m.group(1), m.group(2)


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
    try:
        owner, album = parse_owner_album(album_url)
        r = session.get("https://api.vk.com/method/photos.get", params={
            "owner_id": owner, "album_id": album, "count": 1000,
            "photo_sizes": 1, "access_token": token, "v": API_VERSION,
        }, timeout=cfg.request_timeout)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            return None
        photos = photos_to_models(data)
        if not photos:
            return None
        title = f"album{owner}_{album}"
        return photos, title
    except Exception:
        return None
