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
