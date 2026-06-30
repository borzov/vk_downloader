"""Core domain models shared across sources and the downloader."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Photo:
    id: str
    urls: list
