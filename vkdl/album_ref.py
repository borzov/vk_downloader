"""Album identity: the single place that knows the VK album URL shape.

Both URL validation (CLI) and owner/album extraction (API source) go through
``parse`` so the format lives in exactly one regex.
"""
import re
from dataclasses import dataclass

_ALBUM_URL_RE = re.compile(r"https?://vk\.com/album(-?\d+)_(\d+)")


@dataclass(frozen=True)
class AlbumRef:
    owner_id: str
    album_id: str


def parse(url: str) -> "AlbumRef | None":
    m = _ALBUM_URL_RE.match(url)
    if not m:
        return None
    return AlbumRef(owner_id=m.group(1), album_id=m.group(2))


def is_album_url(url: str) -> bool:
    return parse(url) is not None
