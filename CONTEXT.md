# vk_downloader

Fetches photos from public VK albums: token-free scraping by default, the
official VK API as an optional faster path when a token is present.

## Language

**Album**:
The photos of one VK album together with its title — the unit everything
downstream works on.
_Avoid_: playlist, collection, the bare `(photos, title)` tuple

**AlbumRef**:
The identity of an album — owner id plus album id — parsed from an album URL.
_Avoid_: album id (ambiguous: that is only half of it), url params

**Source**:
An adapter that produces an Album from an album URL, or passes when it has no
result. The two adapters are the API source (token) and the scraper.
_Avoid_: provider, backend, fetcher, resolver step

**Resolution chain**:
Sources tried in order; the first one that produces an Album wins.
_Avoid_: pipeline, fallback stack

**Download job**:
One album brought from URL to files on disk: resolve, name the folder,
download, deduplicate, count. The CLI and the batch loop are thin shells over
download jobs.
_Avoid_: task, run, request

**DownloadReport**:
The outcome of a download job — status, title, directory, counters. Complete
outcome of one call; never hides unexpected bugs.
_Avoid_: result, response, stats

**Batch task**:
One row of the batch CSV: name, date, album link. Feeds a download job with a
custom folder title.
_Avoid_: job (a job is the download itself), entry

**Dedup index**:
The registry of already-saved photo content, keyed by hash; identical bytes
are saved once, the second copy is reported as a duplicate.
_Avoid_: cache
