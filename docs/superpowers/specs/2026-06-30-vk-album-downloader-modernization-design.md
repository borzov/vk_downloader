# VK Album Downloader — Modernization Design

**Date:** 2026-06-30
**Status:** Approved (design); spec pending user review
**Scope target:** Photos from VK albums (NOT video). Confirmed by user.

## 1. Context & Problem

Current repo is a single 722-line monolith `vk_downloader.py` that downloads
**photos** from **public** VK albums via HTML scraping + AJAX pagination.

### Diagnostic findings (verified live 2026-06-30 on album-18515186_240802273)

| Node | Status | Detail |
|---|---|---|
| HTML parse `.photos_row` | WORKS | 40 photos on first page; title + count parsed |
| AJAX pagination (`offset`) | WORKS | `offset=40` returns next 40, JSON shape unchanged |
| Max-quality availability | AVAILABLE but algo suboptimal | `as` sizes up to 2560x1920 exist |
| `get_all_quality_urls` quality pick | DEFECT | first candidate is URL **without params** -> always HTTP 404 (wasted request per photo); `cs` formation is heuristic, not guaranteed max |

**Conclusion:** scraping is NOT broken. Real weaknesses: (1) fragile coupling to
markup, (2) broken quality selection with guaranteed 404, (3) no auth -> private
albums inaccessible, (4) no rate-limit/retry -> ban risk at 20 threads, (5)
monolith without tests.

## 2. Decisions (user-selected)

- **Q1 = A** — Target is PHOTOS (album downloader), not video. "Video" was a slip.
- **Q2 = C** — HYBRID data source: official VK API primary, scraping fallback.
- **Q3 = B** — MODERATE refactor: extract 4-5 modules, add API branch + tests on
  key nodes. No total rewrite.

## 3. Architecture (moderate refactor)

Extract monolith into focused modules (each 200-400 lines, <800 max):

```
vk_downloader.py          # thin CLI entrypoint (arg parse, mode dispatch)
vkdl/
  __init__.py
  config.py               # HEADERS, timeouts, retry/rate-limit constants, no hardcoded secrets
  api_client.py           # VK API path: photos.get -> direct sized URLs (token via env VK_ACCESS_TOKEN)
  scraper.py              # fallback: HTML + AJAX pagination (current logic, cleaned)
  quality.py              # FIXED quality selection (see 3.1)
  downloader.py           # threaded download, SHA256 dedup, retry/backoff, rate-limit
  batch.py                # CSV batch mode (Name;DateStart;AlbumLink)
tests/
  test_quality.py
  test_scraper.py
  test_api_client.py
  test_downloader.py
```

### 3.1 Quality selection fix (core defect)

- Drop the always-404 "base URL without params" first candidate.
- Pick the **largest** size from `as` list, build the correct `cs` param to
  request the true maximum, then descend on 404.
- API path bypasses this entirely: VK returns labeled sizes (w,z,y,x...) with
  direct URLs — pick highest available.

### 3.2 Hybrid flow

```
if VK_ACCESS_TOKEN present:
    try API (photos.get) -> sized URLs       # robust, handles accessible private albums
    on API failure/no-token -> fall back to scraper
else:
    scraper path (public albums only)
```

### 3.3 Resilience (new)

- Session-level retry with exponential backoff (configurable, no hardcode).
- Polite rate-limit between requests; cap effective concurrency.
- Keep current behaviors: resume (skip existing), SHA256 dedup, temp-file rename.

## 4. Data flow

URL/CSV -> resolve source (API|scraper) -> list of {id, sized_urls} ->
threaded downloader (retry, dedup) -> album folder.

## 5. Error handling

- Explicit, user-friendly messages (no internals leaked).
- Distinguish: private/closed album, 404 photo, network/timeout, captcha/ban.

## 6. Testing (TDD, target 80%)

- Unit: quality selection (largest size, cs formation, 404 descent), CSV parse,
  filename sanitize, dedup hashing.
- Integration (mocked HTTP): scraper pagination, API response mapping, downloader
  retry path. No live VK in CI.

## 7. Backward compatibility

- Preserve CLI: `vk_downloader.py <album_url> [threads]` and
  `--batch <csv> [threads]`. Same album folder naming.

## 8. Out of scope (YAGNI)

- Video download (explicitly deferred — separate future module if ever needed).
- GUI, scheduling, cloud upload.
