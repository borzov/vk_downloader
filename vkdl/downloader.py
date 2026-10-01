"""Threaded photo download with SHA256 dedup."""
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests
from .config import DownloadConfig
from .dedup import DedupIndex, file_sha256
from .http import get as http_get
from .quality import guess_extension


def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def download_photo(photo, idx: int, album_dir: Path, session, cfg: DownloadConfig,
                   index: DedupIndex = None) -> dict:
    if index is None:
        index = DedupIndex.from_dir(album_dir)
    ext = guess_extension(photo.urls[0]) if photo.urls else ".jpg"
    filename = f"{idx:03d}_{photo.id.replace('-', '_')}{ext}"
    filepath = album_dir / filename
    if filepath.exists():
        return {"status": "skipped", "idx": idx, "filename": filename}

    last_error = "all URLs failed"
    for url in photo.urls:
        try:
            r = http_get(session, url, cfg, stream=True)
            if r.status_code == 404:
                continue
            tmp = filepath.with_suffix(filepath.suffix + ".tmp")
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            dup = index.claim(file_sha256(tmp), filename)
            if dup:
                tmp.unlink()
                return {"status": "duplicate", "idx": idx, "filename": filename,
                        "duplicate_name": dup}
            tmp.rename(filepath)
            return {"status": "success", "idx": idx, "filename": filename}
        except requests.RequestException as e:
            # network failure on this URL: remember it and try the next size
            last_error = str(e)
            continue
    return {"status": "error", "idx": idx, "filename": filename, "error": last_error}


def download_all(photos, album_dir: Path, session, cfg: DownloadConfig) -> dict:
    album_dir.mkdir(exist_ok=True)
    index = DedupIndex.from_dir(album_dir)
    counters = {"success": 0, "skipped": 0, "duplicate": 0, "error": 0}
    args = [(p, i) for i, p in enumerate(photos, 1)]
    with ThreadPoolExecutor(max_workers=cfg.max_workers) as ex:
        futures = {ex.submit(download_photo, p, i, album_dir, session, cfg, index): i
                   for p, i in args}
        for fut in as_completed(futures):
            res = fut.result()
            counters[res["status"]] = counters.get(res["status"], 0) + 1
    return counters
