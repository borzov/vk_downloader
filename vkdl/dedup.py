"""Content dedup index.

Hashes the album's existing images once, then answers "is this content already
here?" in O(1). ``claim`` is an atomic check-and-take so concurrent download
threads cannot both save the same bytes.
"""
import hashlib
import threading
from pathlib import Path

_IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(4096), b""):
            h.update(block)
    return h.hexdigest()


class DedupIndex:
    def __init__(self):
        self._owner = {}  # content hash -> filename that owns it
        self._lock = threading.Lock()

    @classmethod
    def from_dir(cls, album_dir: Path) -> "DedupIndex":
        idx = cls()
        for p in album_dir.glob("*.*"):
            if p.is_file() and p.suffix.lower() in _IMG_EXT:
                idx.claim(file_sha256(p), p.name)
        return idx

    def claim(self, file_hash: str, name: str) -> "str | None":
        """Take ``file_hash`` for ``name``. Return the existing owner's name if
        the hash is already claimed, else ``None``."""
        with self._lock:
            existing = self._owner.get(file_hash)
            if existing is not None:
                return existing
            self._owner[file_hash] = name
            return None
