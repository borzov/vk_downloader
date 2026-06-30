"""Threaded photo download with retry/backoff and SHA256 dedup."""
import hashlib
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests
from .config import HEADERS, DownloadConfig
from .quality import guess_extension


def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(4096), b""):
            h.update(block)
    return h.hexdigest()


def _find_duplicate(album_dir: Path, file_hash: str, current: str) -> Path | None:
    for p in album_dir.glob("*.*"):
        if p.name == current or not p.is_file():
            continue
        if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            if file_sha256(p) == file_hash:
                return p
    return None


def _get_with_retry(session, url, cfg):
    last = None
    for attempt in range(cfg.retries):
        try:
            r = session.get(url, headers=HEADERS, stream=True, timeout=cfg.request_timeout)
            if r.status_code == 404:
                return r
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            time.sleep(cfg.backoff_base * (2 ** attempt))
    raise last if last else requests.RequestException("unknown")


def download_photo(photo, idx: int, album_dir: Path, session, cfg: DownloadConfig) -> dict:
    ext = guess_extension(photo.urls[0]) if photo.urls else ".jpg"
    filename = f"{idx:03d}_{photo.id.replace('-', '_')}{ext}"
    filepath = album_dir / filename
    if filepath.exists():
        return {"status": "skipped", "idx": idx, "filename": filename}

    last_error = "all URLs failed"
    for url in photo.urls:
        try:
            r = _get_with_retry(session, url, cfg)
            if r.status_code == 404:
                continue
            tmp = filepath.with_suffix(filepath.suffix + ".tmp")
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            fh = file_sha256(tmp)
            dup = _find_duplicate(album_dir, fh, filename)
            if dup:
                tmp.unlink()
                return {"status": "duplicate", "idx": idx, "filename": filename,
                        "duplicate_name": dup.name}
            tmp.rename(filepath)
            return {"status": "success", "idx": idx, "filename": filename}
        except requests.RequestException as e:
            # network failure on this URL: remember it and try the next size
            last_error = str(e)
            continue
    return {"status": "error", "idx": idx, "filename": filename, "error": last_error}


def download_all(photos, album_dir: Path, session, cfg: DownloadConfig) -> dict:
    album_dir.mkdir(exist_ok=True)
    counters = {"success": 0, "skipped": 0, "duplicate": 0, "error": 0}
    args = [(p, i) for i, p in enumerate(photos, 1)]
    with ThreadPoolExecutor(max_workers=cfg.max_workers) as ex:
        futures = {ex.submit(download_photo, p, i, album_dir, session, cfg): i for p, i in args}
        for fut in as_completed(futures):
            res = fut.result()
            counters[res["status"]] = counters.get(res["status"], 0) + 1
    return counters
