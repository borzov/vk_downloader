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
