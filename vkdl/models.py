"""Core domain models shared across sources and the downloader."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Photo:
    id: str
    urls: list


@dataclass(frozen=True)
class Album:
    """What every source produces: photos plus the album's title."""
    photos: list
    title: str
    source: str  # which adapter produced it: "api" | "scraper"
