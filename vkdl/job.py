"""Download jobs: one album from URL to files on disk.

``download_album`` is the package's front door: resolve the album, name the
folder, download with dedup, and return a complete :class:`DownloadReport`.
Expected failures (network error, empty/closed album) arrive in the report;
unexpected bugs propagate unmasked.
"""
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import requests

from .config import DownloadConfig, get_access_token
from .downloader import download_all, sanitize_filename
from .http import make_session
from .resolver import resolve_album

JobStatus = Literal["ok", "network_error", "empty"]


@dataclass(frozen=True)
class DownloadReport:
    status: JobStatus
    title: str = ""
    album_dir: Path | None = None
    counters: dict = field(default_factory=dict)
    elapsed: float = 0.0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def download_album(album_url: str, *, max_workers: int = 5,
                   custom_title: str = None, out_base: Path = Path("."),
                   sources=None) -> DownloadReport:
    """Run one download job and report the complete outcome."""
    session = make_session()
    cfg = DownloadConfig(max_workers=max_workers)
    start = time.perf_counter()
    try:
        token = get_access_token()
        photos, title = resolve_album(album_url, session, cfg, token=token,
                                      sources=sources)
    except requests.RequestException as e:
        return DownloadReport(status="network_error", title=custom_title or "",
                              elapsed=time.perf_counter() - start, error=str(e))
    if not photos:
        return DownloadReport(status="empty", title=title,
                              elapsed=time.perf_counter() - start)
    folder = sanitize_filename(custom_title or title)
    album_dir = Path(out_base) / folder
    counters = download_all(photos, album_dir, session, cfg)
    return DownloadReport(status="ok", title=folder, album_dir=album_dir,
                          counters=counters,
                          elapsed=time.perf_counter() - start)
