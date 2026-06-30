# VK Album Downloader Modernization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the 722-line monolith into a focused `vkdl/` package, fix the broken photo quality selection, and add resilient downloading — fully working without a VK token, with an optional token-only API acceleration branch.

**Architecture:** Token-free scraping (HTML + AJAX) is the primary, complete path. An optional `api_client` is used only when `VK_ACCESS_TOKEN` is set, falling back to the scraper on any failure. A thin `vk_downloader.py` CLI dispatches single/batch modes. Each module has one responsibility and its own tests.

**Tech Stack:** Python 3.10+ (PEP 604 `X | None` syntax used throughout), `requests`, `beautifulsoup4`, `pytest` (+ `responses` for mocked HTTP). Runner: `uv` (`/opt/homebrew/bin/uv`).

## Global Constraints

- Target = PHOTOS from PUBLIC VK albums only. No video, no private albums, no login/auth.
- Product MUST work end-to-end with NO token. `VK_ACCESS_TOKEN` is optional-only.
- No hardcoded secrets/URLs/limits — all tunables in `vkdl/config.py`.
- Files 200-400 lines typical, 800 max. Immutability: never mutate inputs, return new objects.
- TDD mandatory: test fails (RED) before implementation (GREEN). Target 80% coverage.
- Preserve CLI: `vk_downloader.py <album_url> [threads]` and `--batch <csv> [threads]`. Same album folder naming.
- Conventional commits. No "Claude" co-author.
- Run tests via: `/opt/homebrew/bin/uv run --with requests --with beautifulsoup4 --with pytest --with responses pytest -q`

---

### Task 1: Package skeleton + config

**Files:**
- Create: `vkdl/__init__.py`
- Create: `vkdl/config.py`
- Create: `tests/__init__.py`
- Create: `tests/test_config.py`
- Modify: `pyproject.toml` (add `[dependency-groups]` dev deps: pytest, responses)

**Interfaces:**
- Produces:
  - `vkdl.config.HEADERS: dict` — base HTTP headers (Chrome/Safari UA, ru locale)
  - `vkdl.config.DownloadConfig` dataclass with fields: `max_workers:int=5`, `request_timeout:int=30`, `retries:int=3`, `backoff_base:float=0.5`, `rate_limit_delay:float=0.5`, `ajax_page_size:int=40`
  - `vkdl.config.get_access_token() -> str | None` — reads `VK_ACCESS_TOKEN` env, returns None if unset/empty
  - `vkdl.config.MAX_WORKERS_LIMIT:int=20`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import os
from vkdl import config

def test_headers_have_browser_ua():
    assert "User-Agent" in config.HEADERS
    assert "Mozilla/5.0" in config.HEADERS["User-Agent"]

def test_default_download_config():
    c = config.DownloadConfig()
    assert c.max_workers == 5
    assert c.retries == 3
    assert c.ajax_page_size == 40

def test_get_access_token_absent(monkeypatch):
    monkeypatch.delenv("VK_ACCESS_TOKEN", raising=False)
    assert config.get_access_token() is None

def test_get_access_token_present(monkeypatch):
    monkeypatch.setenv("VK_ACCESS_TOKEN", "tok123")
    assert config.get_access_token() == "tok123"

def test_get_access_token_empty_is_none(monkeypatch):
    monkeypatch.setenv("VK_ACCESS_TOKEN", "")
    assert config.get_access_token() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/opt/homebrew/bin/uv run --with requests --with beautifulsoup4 --with pytest --with responses pytest tests/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'vkdl'`

- [ ] **Step 3: Write minimal implementation**

```python
# vkdl/__init__.py
"""VK album photo downloader package."""
```

```python
# vkdl/config.py
"""Central configuration: headers, tunables, optional token. No hardcoded secrets."""
import os
from dataclasses import dataclass

MAX_WORKERS_LIMIT = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


@dataclass(frozen=True)
class DownloadConfig:
    max_workers: int = 5
    request_timeout: int = 30
    retries: int = 3
    backoff_base: float = 0.5
    rate_limit_delay: float = 0.5
    ajax_page_size: int = 40


def get_access_token() -> str | None:
    token = os.environ.get("VK_ACCESS_TOKEN", "").strip()
    return token or None
```

```python
# tests/__init__.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/opt/homebrew/bin/uv run --with requests --with beautifulsoup4 --with pytest --with responses pytest tests/test_config.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Update pyproject dev deps**

```toml
# append to pyproject.toml
[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "responses>=0.25.0",
]
```

- [ ] **Step 6: Commit**

```bash
git add vkdl/__init__.py vkdl/config.py tests/__init__.py tests/test_config.py pyproject.toml
git commit -m "feat: add vkdl package skeleton and config"
```

---

### Task 2: Quality selection fix (core defect)

The defect: `get_all_quality_urls` puts a no-params base URL first → guaranteed
HTTP 404 per photo. Fix: rank VK `as` sizes descending, build correct `cs`, no
dead first candidate.

**Files:**
- Create: `vkdl/quality.py`
- Create: `tests/test_quality.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `vkdl.quality.extract_quality_urls(style_url: str) -> list[str]` — given a CSS `url(...)` string (or raw URL), returns candidate image URLs ordered highest→lowest quality, no guaranteed-404 entries.
  - `vkdl.quality.guess_extension(url: str) -> str` — returns `.jpg`/`.png`/`.webp`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_quality.py
from vkdl.quality import extract_quality_urls, guess_extension

STYLE = (
    "background-image:url(https://sun9.userapi.com/impf/abc/photo.jpg"
    "?quality=96&as=32x24,160x120,1280x960,2560x1920&from=bu&cs=240x0)"
)

def test_returns_urls_highest_first():
    urls = extract_quality_urls(STYLE)
    assert urls, "must produce at least one candidate"
    # largest size (2560) must come before smaller ones
    assert "2560" in urls[0]
    big = next(i for i, u in enumerate(urls) if "2560" in u)
    small = next(i for i, u in enumerate(urls) if "160x120" in u or "cs=160" in u)
    assert big < small

def test_no_paramless_base_first_candidate():
    urls = extract_quality_urls(STYLE)
    # the bare path without query was the old always-404 entry; it must not lead
    assert "?" in urls[0], "first candidate must carry sizing params"

def test_raw_url_without_css_wrapper():
    raw = "https://sun9.userapi.com/impf/x/p.jpg?as=100x100,800x600&cs=100x0"
    urls = extract_quality_urls(raw)
    assert any("800" in u for u in urls)

def test_no_match_returns_empty():
    assert extract_quality_urls("background:none") == []

def test_guess_extension():
    assert guess_extension("https://x/p.png?as=1") == ".png"
    assert guess_extension("https://x/p.webp") == ".webp"
    assert guess_extension("https://x/p.jpg?q=1") == ".jpg"
    assert guess_extension("https://x/p") == ".jpg"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/opt/homebrew/bin/uv run --with requests --with beautifulsoup4 --with pytest --with responses pytest tests/test_quality.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'vkdl.quality'`

- [ ] **Step 3: Write minimal implementation**

```python
# vkdl/quality.py
"""Photo quality URL selection. Ranks VK `as` sizes descending; no dead 404 lead."""
import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

_URL_IN_CSS = re.compile(r"url\((https?://[^)]+)\)")


def _extract_url(style_or_url: str) -> str | None:
    m = _URL_IN_CSS.search(style_or_url)
    if m:
        return m.group(1)
    if style_or_url.startswith("http"):
        return style_or_url.strip()
    return None


def _size_width(size: str) -> int:
    try:
        return int(size.split("x")[0])
    except (ValueError, IndexError):
        return 0


def extract_quality_urls(style_or_url: str) -> list[str]:
    url = _extract_url(style_or_url)
    if not url:
        return []

    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    sizes = params.get("as", [""])[0].split(",") if params.get("as") else []
    sizes = [s for s in sizes if s]
    current_cs = params.get("cs", [""])[0]

    urls: list[str] = []
    for size in sorted(sizes, key=_size_width, reverse=True):
        new_params = dict(params)
        if current_cs.endswith("x0"):
            new_params["cs"] = [f"{_size_width(size)}x0"]
        else:
            new_params["cs"] = [size]
        query = urlencode(new_params, doseq=True)
        urls.append(urlunparse((
            parsed.scheme, parsed.netloc, parsed.path,
            parsed.params, query, parsed.fragment,
        )))

    if url not in urls:
        urls.append(url)  # original as final fallback (still parametrized)
    return urls


def guess_extension(url: str) -> str:
    path = urlparse(url).path.lower()
    if path.endswith(".png"):
        return ".png"
    if path.endswith(".webp"):
        return ".webp"
    return ".jpg"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/opt/homebrew/bin/uv run --with requests --with beautifulsoup4 --with pytest --with responses pytest tests/test_quality.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add vkdl/quality.py tests/test_quality.py
git commit -m "fix: rank photo quality by size, drop always-404 lead candidate"
```

---

### Task 3: Scraper (HTML parse + AJAX pagination)

**Files:**
- Create: `vkdl/scraper.py`
- Create: `tests/test_scraper.py`

**Interfaces:**
- Consumes: `vkdl.quality.extract_quality_urls`, `vkdl.config.HEADERS/DownloadConfig`
- Produces:
  - `vkdl.scraper.Photo` dataclass: `id: str`, `urls: list[str]`
  - `vkdl.scraper.parse_photos(html: str) -> list[Photo]` — extracts `.photos_row` rows.
  - `vkdl.scraper.parse_album_meta(html: str) -> tuple[str, int]` — `(title, total_count)`.
  - `vkdl.scraper.extract_ajax_html(ajax_json_text: str) -> str | None` — pulls HTML fragment from AJAX payload.
  - `vkdl.scraper.scrape_album(album_url, session, cfg) -> tuple[list[Photo], str]` — full album via initial page + AJAX loop.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scraper.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/opt/homebrew/bin/uv run --with requests --with beautifulsoup4 --with pytest --with responses pytest tests/test_scraper.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'vkdl.scraper'`

- [ ] **Step 3: Write minimal implementation**

```python
# vkdl/scraper.py
"""Token-free album scraping: HTML parse + AJAX pagination."""
import json
import time
from dataclasses import dataclass
from bs4 import BeautifulSoup
from .quality import extract_quality_urls
from .config import HEADERS, DownloadConfig


@dataclass(frozen=True)
class Photo:
    id: str
    urls: list


def parse_photos(html: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    photos = []
    for row in soup.select(".photos_row"):
        pid = row.get("data-id", "")
        urls = extract_quality_urls(row.get("style", ""))
        if pid and urls:
            photos.append(Photo(id=pid, urls=urls))
    return photos


def parse_album_meta(html: str) -> tuple:
    soup = BeautifulSoup(html, "html.parser")
    title_el = soup.select_one(".photos_album_intro h1")
    title = title_el.text.strip() if title_el else "VK_Album"
    count_el = soup.select_one(".ui_crumb_count")
    try:
        count = int(count_el.text.strip()) if count_el else 0
    except ValueError:
        count = 0
    return title, count


def extract_ajax_html(ajax_json_text: str) -> str | None:
    try:
        data = json.loads(ajax_json_text)
    except (json.JSONDecodeError, ValueError):
        return None
    payload = data.get("payload")
    if not isinstance(payload, list):
        return None
    for item in payload:
        if isinstance(item, list):
            for sub in item:
                if isinstance(sub, str) and "<div" in sub:
                    return sub
    return None


def scrape_album(album_url: str, session, cfg: DownloadConfig = DownloadConfig()) -> tuple:
    resp = session.get(album_url, headers=HEADERS, timeout=cfg.request_timeout)
    resp.raise_for_status()
    title, total = parse_album_meta(resp.text)
    photos = list(parse_photos(resp.text))

    offset = len(photos)
    ajax_headers = {**HEADERS, "Content-Type": "application/x-www-form-urlencoded",
                    "X-Requested-With": "XMLHttpRequest", "Accept": "*/*",
                    "Origin": "https://vk.com", "Referer": album_url}
    while offset < total:
        data = {"al": "1", "offset": str(offset), "part": "1", "rev": ""}
        ar = session.post(album_url, data=data, headers=ajax_headers, timeout=cfg.request_timeout)
        ar.raise_for_status()
        html = extract_ajax_html(ar.text)
        if not html:
            break
        new = parse_photos(html)
        if not new:
            break
        photos.extend(new)
        offset = len(photos)
        time.sleep(cfg.rate_limit_delay)
    return photos, title
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/opt/homebrew/bin/uv run --with requests --with beautifulsoup4 --with pytest --with responses pytest tests/test_scraper.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add vkdl/scraper.py tests/test_scraper.py
git commit -m "feat: add scraper module with HTML parse and AJAX pagination"
```

---

### Task 4: Downloader (threaded, retry/backoff, SHA256 dedup)

**Files:**
- Create: `vkdl/downloader.py`
- Create: `tests/test_downloader.py`

**Interfaces:**
- Consumes: `vkdl.scraper.Photo`, `vkdl.quality.guess_extension`, `vkdl.config`
- Produces:
  - `vkdl.downloader.sanitize_filename(name: str) -> str`
  - `vkdl.downloader.file_sha256(path: Path) -> str`
  - `vkdl.downloader.download_photo(photo, idx, album_dir, session, cfg) -> dict` — tries URLs high→low, retries with backoff, returns `{"status": "success|skipped|duplicate|error", "idx", "filename", ...}`. Skips existing; dedup by hash.
  - `vkdl.downloader.download_all(photos, album_dir, session, cfg) -> dict` — threaded; returns counters dict.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_downloader.py
from pathlib import Path
import responses
import requests
from vkdl.downloader import sanitize_filename, file_sha256, download_photo
from vkdl.scraper import Photo
from vkdl.config import DownloadConfig

def test_sanitize_filename():
    assert sanitize_filename('a/b:c*?.jpg') == 'a_b_c__.jpg'

def test_file_sha256(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"hello")
    assert file_sha256(p) == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )

@responses.activate
def test_download_photo_success(tmp_path):
    url = "https://s/p.jpg?as=10x10&cs=10x0"
    responses.add(responses.GET, "https://s/p.jpg", body=b"IMGDATA", status=200)
    photo = Photo(id="1_2", urls=[url])
    s = requests.Session()
    res = download_photo(photo, 1, tmp_path, s, DownloadConfig(retries=1))
    assert res["status"] == "success"
    assert (tmp_path / res["filename"]).read_bytes() == b"IMGDATA"

@responses.activate
def test_download_photo_skips_existing(tmp_path):
    url = "https://s/p.jpg?as=10x10&cs=10x0"
    photo = Photo(id="1_2", urls=[url])
    existing = tmp_path / "001_1_2.jpg"
    existing.write_bytes(b"X")
    s = requests.Session()
    res = download_photo(photo, 1, tmp_path, s, DownloadConfig())
    assert res["status"] == "skipped"

@responses.activate
def test_download_photo_falls_to_next_url_on_404(tmp_path):
    big = "https://s/p.jpg?as=99x99&cs=99x0"
    small = "https://s/p.jpg?as=10x10&cs=10x0"
    responses.add(responses.GET, "https://s/p.jpg", status=404)
    responses.add(responses.GET, "https://s/p.jpg", body=b"SMALL", status=200)
    photo = Photo(id="1_2", urls=[big, small])
    s = requests.Session()
    res = download_photo(photo, 1, tmp_path, s, DownloadConfig(retries=1))
    assert res["status"] == "success"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/opt/homebrew/bin/uv run --with requests --with beautifulsoup4 --with pytest --with responses pytest tests/test_downloader.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'vkdl.downloader'`

- [ ] **Step 3: Write minimal implementation**

```python
# vkdl/downloader.py
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
            return {"status": "error", "idx": idx, "filename": filename, "error": str(e)}
    return {"status": "error", "idx": idx, "filename": filename, "error": "all URLs failed"}


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/opt/homebrew/bin/uv run --with requests --with beautifulsoup4 --with pytest --with responses pytest tests/test_downloader.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add vkdl/downloader.py tests/test_downloader.py
git commit -m "feat: add threaded downloader with retry, backoff and dedup"
```

---

### Task 5: Optional API client (token-only)

**Files:**
- Create: `vkdl/api_client.py`
- Create: `tests/test_api_client.py`

**Interfaces:**
- Consumes: `vkdl.scraper.Photo`, `vkdl.config`
- Produces:
  - `vkdl.api_client.parse_owner_album(album_url: str) -> tuple[str, str]` — `(owner_id, album_id)` from `vk.com/album-18515186_240802273` → `("-18515186", "240802273")`.
  - `vkdl.api_client.photos_to_models(api_json: dict) -> list[Photo]` — maps `photos.get` response → highest-size-first `Photo` list.
  - `vkdl.api_client.fetch_album(album_url, token, session, cfg) -> tuple[list[Photo], str] | None` — returns None on any failure (caller falls back to scraper).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_client.py
from vkdl.api_client import parse_owner_album, photos_to_models

def test_parse_owner_album_negative_owner():
    owner, album = parse_owner_album("https://vk.com/album-18515186_240802273")
    assert owner == "-18515186"
    assert album == "240802273"

def test_parse_owner_album_positive_owner():
    owner, album = parse_owner_album("https://vk.com/album12345_67890")
    assert owner == "12345"
    assert album == "67890"

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/opt/homebrew/bin/uv run --with requests --with beautifulsoup4 --with pytest --with responses pytest tests/test_api_client.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'vkdl.api_client'`

- [ ] **Step 3: Write minimal implementation**

```python
# vkdl/api_client.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/opt/homebrew/bin/uv run --with requests --with beautifulsoup4 --with pytest --with responses pytest tests/test_api_client.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add vkdl/api_client.py tests/test_api_client.py
git commit -m "feat: add optional token-only VK API client"
```

---

### Task 6: Source resolver (hybrid dispatch)

**Files:**
- Create: `vkdl/resolver.py`
- Create: `tests/test_resolver.py`

**Interfaces:**
- Consumes: `vkdl.api_client.fetch_album`, `vkdl.scraper.scrape_album`, `vkdl.config.get_access_token`
- Produces:
  - `vkdl.resolver.resolve_album(album_url, session, cfg, token=None, api_fn=..., scrape_fn=...) -> tuple[list[Photo], str]` — if token present, try API; on None or no token, use scraper. `api_fn`/`scrape_fn` injectable for tests.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_resolver.py
from vkdl.resolver import resolve_album
from vkdl.scraper import Photo
from vkdl.config import DownloadConfig

def _scrape_stub(url, session, cfg):
    return [Photo(id="s_1", urls=["scraped"])], "ScrapeTitle"

def test_uses_scraper_when_no_token():
    photos, title = resolve_album("u", None, DownloadConfig(), token=None,
                                  api_fn=lambda *a, **k: None, scrape_fn=_scrape_stub)
    assert title == "ScrapeTitle"
    assert photos[0].id == "s_1"

def test_uses_api_when_token_and_success():
    def api_ok(url, token, session, cfg):
        return [Photo(id="a_1", urls=["api"])], "ApiTitle"
    photos, title = resolve_album("u", None, DownloadConfig(), token="tok",
                                  api_fn=api_ok, scrape_fn=_scrape_stub)
    assert title == "ApiTitle"

def test_falls_back_to_scraper_when_api_returns_none():
    photos, title = resolve_album("u", None, DownloadConfig(), token="tok",
                                  api_fn=lambda *a, **k: None, scrape_fn=_scrape_stub)
    assert title == "ScrapeTitle"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/opt/homebrew/bin/uv run --with requests --with beautifulsoup4 --with pytest --with responses pytest tests/test_resolver.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'vkdl.resolver'`

- [ ] **Step 3: Write minimal implementation**

```python
# vkdl/resolver.py
"""Hybrid source dispatch: optional API first (token-only), scraper fallback."""
from .api_client import fetch_album as _default_api
from .scraper import scrape_album as _default_scrape
from .config import DownloadConfig


def resolve_album(album_url, session, cfg: DownloadConfig, token=None,
                  api_fn=_default_api, scrape_fn=_default_scrape):
    if token:
        result = api_fn(album_url, token, session, cfg)
        if result is not None:
            return result
    return scrape_fn(album_url, session, cfg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/opt/homebrew/bin/uv run --with requests --with beautifulsoup4 --with pytest --with responses pytest tests/test_resolver.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add vkdl/resolver.py tests/test_resolver.py
git commit -m "feat: add hybrid source resolver with scraper fallback"
```

---

### Task 7: Batch CSV parsing

**Files:**
- Create: `vkdl/batch.py`
- Create: `tests/test_batch.py`

**Interfaces:**
- Consumes: nothing (pure parsing)
- Produces:
  - `vkdl.batch.BatchTask` dataclass: `name: str`, `date: str`, `album_url: str`
  - `vkdl.batch.parse_csv(path: str) -> list[BatchTask]` — handles `;`/`,` delimiter, BOM, case-insensitive headers `Name/DateStart/AlbumLink`, date normalization to `YYYY-MM-DD`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_batch.py
from vkdl.batch import parse_csv

def test_parse_csv_semicolon(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("Name;DateStart;AlbumLink\n"
                 "Event;2024-12-25 18:00:00;https://vk.com/album-1_2\n",
                 encoding="utf-8")
    tasks = parse_csv(str(f))
    assert len(tasks) == 1
    assert tasks[0].name == "Event"
    assert tasks[0].date == "2024-12-25"
    assert tasks[0].album_url == "https://vk.com/album-1_2"

def test_parse_csv_comma_and_bom(tmp_path):
    f = tmp_path / "b.csv"
    f.write_text("﻿Name,DateStart,AlbumLink\nX,2024-07-15,https://vk.com/album-3_4\n",
                 encoding="utf-8")
    tasks = parse_csv(str(f))
    assert tasks[0].date == "2024-07-15"

def test_parse_csv_skips_incomplete_rows(tmp_path):
    f = tmp_path / "c.csv"
    f.write_text("Name;DateStart;AlbumLink\n;;https://vk.com/album-1_2\n",
                 encoding="utf-8")
    assert parse_csv(str(f)) == []

def test_parse_csv_missing_file():
    assert parse_csv("/no/such/file.csv") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/opt/homebrew/bin/uv run --with requests --with beautifulsoup4 --with pytest --with responses pytest tests/test_batch.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'vkdl.batch'`

- [ ] **Step 3: Write minimal implementation**

```python
# vkdl/batch.py
"""CSV batch task parsing. Tolerant of delimiter, BOM, header case, date formats."""
import csv
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BatchTask:
    name: str
    date: str
    album_url: str


def _norm_date(raw: str) -> str:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw


def parse_csv(path: str) -> list:
    tasks = []
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            first = f.readline()
            f.seek(0)
            delim = ";" if ";" in first else ","
            reader = csv.DictReader(f, delimiter=delim)
            for row in reader:
                low = {k.lower().strip(): (v or "").strip() for k, v in row.items()}
                name = low.get("name", "")
                date = low.get("datestart", "")
                url = low.get("albumlink", "")
                if not (name and date and url):
                    continue
                tasks.append(BatchTask(name=name, date=_norm_date(date), album_url=url))
        return tasks
    except FileNotFoundError:
        return []
    except Exception:
        return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/opt/homebrew/bin/uv run --with requests --with beautifulsoup4 --with pytest --with responses pytest tests/test_batch.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add vkdl/batch.py tests/test_batch.py
git commit -m "feat: add CSV batch task parser"
```

---

### Task 8: CLI entrypoint + integration

Rewrite `vk_downloader.py` as a thin orchestrator over `vkdl/`. Preserve exact CLI.

**Files:**
- Modify: `vk_downloader.py` (replace monolith body; keep shebang + docstring)
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: `vkdl.config`, `vkdl.resolver.resolve_album`, `vkdl.downloader.download_all`, `vkdl.batch.parse_csv`, `vkdl.downloader.sanitize_filename`
- Produces:
  - `vk_downloader.run_single(album_url, max_workers, custom_title=None) -> bool`
  - `vk_downloader.validate_url(url: str) -> bool`
  - `vk_downloader.main(argv: list[str]) -> int`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location(
    "vk_dl_cli", pathlib.Path(__file__).parent.parent / "vk_downloader.py")
cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)

def test_validate_url_accepts_album():
    assert cli.validate_url("https://vk.com/album-18515186_240802273")
    assert cli.validate_url("https://vk.com/album12345_67890")

def test_validate_url_rejects_garbage():
    assert not cli.validate_url("https://vk.com/video-1_2")
    assert not cli.validate_url("not a url")

def test_main_no_args_returns_error_code():
    assert cli.main([]) == 1

def test_main_bad_url_returns_error_code():
    assert cli.main(["https://vk.com/video-1_2"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/opt/homebrew/bin/uv run --with requests --with beautifulsoup4 --with pytest --with responses pytest tests/test_cli.py -q`
Expected: FAIL — `AttributeError: module 'vk_dl_cli' has no attribute 'validate_url'`

- [ ] **Step 3: Write minimal implementation**

```python
#!/usr/bin/env python3
"""VK Album Photo Downloader — thin CLI over the vkdl package.
Usage:
  uv run vk_downloader.py <album_url> [threads]
  uv run vk_downloader.py --batch <csv> [threads]
"""
import re
import sys
import time
from pathlib import Path
import requests
from vkdl.config import HEADERS, DownloadConfig, get_access_token, MAX_WORKERS_LIMIT
from vkdl.resolver import resolve_album
from vkdl.downloader import download_all, sanitize_filename
from vkdl.batch import parse_csv

_URL_RE = re.compile(r"https?://vk\.com/album-?\d+_\d+")


def validate_url(url: str) -> bool:
    return bool(_URL_RE.match(url))


def run_single(album_url: str, max_workers: int, custom_title: str = None) -> bool:
    session = requests.Session()
    cfg = DownloadConfig(max_workers=max_workers)
    token = get_access_token()
    photos, title = resolve_album(album_url, session, cfg, token=token)
    if not photos:
        print("❌ Фотографии не найдены (альбом закрыт или пуст).")
        return False
    title = sanitize_filename(custom_title or title)
    album_dir = Path(title)
    print(f"📁 Папка: {album_dir.absolute()} | потоков: {max_workers}")
    start = time.time()
    counters = download_all(photos, album_dir, session, cfg)
    print(f"✅ {counters['success']}  🔗 {counters['duplicate']}  "
          f"⏭️ {counters['skipped']}  ❌ {counters['error']}  "
          f"за {time.time()-start:.1f}с")
    return True


def _run_batch(csv_file: str, max_workers: int) -> None:
    tasks = parse_csv(csv_file)
    if not tasks:
        print("❌ Нет валидных заданий в CSV")
        return
    for i, t in enumerate(tasks, 1):
        print(f"\n=== {i}/{len(tasks)}: {t.name} ({t.date}) ===")
        if not validate_url(t.album_url):
            print("❌ Неверный URL, пропуск")
            continue
        run_single(t.album_url, max_workers, custom_title=f"{t.date} - {t.name}")
        if i < len(tasks):
            time.sleep(2)


def _parse_workers(argv: list, pos: int) -> int:
    w = int(argv[pos]) if len(argv) > pos else 5
    if not 1 <= w <= MAX_WORKERS_LIMIT:
        raise ValueError(f"threads must be 1..{MAX_WORKERS_LIMIT}")
    return w


def main(argv: list) -> int:
    if not argv:
        print("Usage: vk_downloader.py <album_url> [threads] | --batch <csv> [threads]")
        return 1
    try:
        if argv[0] == "--batch":
            if len(argv) < 2:
                print("❌ Не указан CSV файл")
                return 1
            _run_batch(argv[1], _parse_workers(argv, 2))
            return 0
        url = argv[0]
        if not validate_url(url):
            print("❌ Неверный формат URL альбома")
            return 1
        ok = run_single(url, _parse_workers(argv, 1))
        return 0 if ok else 1
    except ValueError as e:
        print(f"❌ {e}")
        return 1
    except KeyboardInterrupt:
        print("\n⚠️ Прервано пользователем")
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/opt/homebrew/bin/uv run --with requests --with beautifulsoup4 --with pytest --with responses pytest tests/test_cli.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Run the FULL suite + smoke check**

Run: `/opt/homebrew/bin/uv run --with requests --with beautifulsoup4 --with pytest --with responses pytest -q`
Expected: all tests PASS (~30 tests)

- [ ] **Step 6: Commit**

```bash
git add vk_downloader.py tests/test_cli.py
git commit -m "refactor: replace monolith with thin CLI over vkdl package"
```

---

### Task 9: Docs + live smoke test

**Files:**
- Modify: `README.md` (note token-free default + optional `VK_ACCESS_TOKEN`, new structure)
- Modify: `pyproject.toml` (bump version to 0.2.0)

- [ ] **Step 1: Live smoke test on a real public album**

Run:
```bash
cd /Users/borzov/Develop/Public/vk_downloader && \
/opt/homebrew/bin/uv run --with requests --with beautifulsoup4 \
  python vk_downloader.py https://vk.com/album-18515186_240802273 5
```
Expected: a folder created, photos downloaded with success counter > 0, no crash.
Verify at least one file opens as a valid image and is larger than the old 240px preview.

- [ ] **Step 2: Update README**

Add a short section: "Работает без токена. Опционально: `export VK_ACCESS_TOKEN=...` ускоряет и стабилизирует через официальный VK API." Document the new `vkdl/` layout briefly. Bump version note to 0.2.0.

- [ ] **Step 3: Bump version**

In `pyproject.toml` set `version = "0.2.0"`.

- [ ] **Step 4: Commit**

```bash
git add README.md pyproject.toml
git commit -m "docs: document token-free default and optional API; bump to 0.2.0"
```

---

## Self-Review Notes

- **Spec coverage:** modular split (T1,3,4,5,6,7,8) ✓; quality fix (T2) ✓; hybrid token-optional (T5,T6) ✓; resilience retry/backoff/rate-limit (T1 config, T3 sleep, T4 retry) ✓; CSV batch (T7) ✓; CLI compat (T8) ✓; tests/80% (every task) ✓; live test (T9) ✓; out-of-scope items untouched ✓.
- **Placeholders:** none — every step has real code/commands.
- **Type consistency:** `Photo(id, urls)` used identically across scraper/api_client/downloader/resolver; `DownloadConfig` fields stable; `resolve_album`/`download_all` signatures match CLI usage.
