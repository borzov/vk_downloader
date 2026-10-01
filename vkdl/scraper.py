"""Token-free album scraping: HTML parse + AJAX pagination."""
import json
import time
from bs4 import BeautifulSoup
from .models import Album, Photo
from .quality import extract_quality_urls
from .config import DownloadConfig
from .http import get as http_get, post as http_post


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


def _ajax_photo_pages(session, album_url, cfg, total, offset):
    """Yield lists of new photos from AJAX pages until ``total`` is reached.

    The offset advances by the rows each page actually contains; an
    unparseable or empty page ends pagination.
    """
    ajax_headers = {"Content-Type": "application/x-www-form-urlencoded",
                    "X-Requested-With": "XMLHttpRequest", "Accept": "*/*",
                    "Origin": "https://vk.com", "Referer": album_url}
    while offset < total:
        data = {"al": "1", "offset": str(offset), "part": "1", "rev": ""}
        ar = http_post(session, album_url, cfg, data=data, headers=ajax_headers)
        html = extract_ajax_html(ar.text)
        if not html:
            return
        new = parse_photos(html)
        if not new:
            return
        yield new
        offset += len(new)
        time.sleep(cfg.rate_limit_delay)


def scrape_album(album_url: str, session,
                 cfg: DownloadConfig = DownloadConfig()):
    """Scraper source: parse the first page, fold the AJAX pages in."""
    resp = http_get(session, album_url, cfg)
    title, total = parse_album_meta(resp.text)
    photos = list(parse_photos(resp.text))
    for new in _ajax_photo_pages(session, album_url, cfg, total, len(photos)):
        photos.extend(new)
    if not photos:
        return None
    return Album(photos=photos, title=title, source="scraper")
