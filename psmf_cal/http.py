"""Polite, cached HTTP access to psmf.cz.

The crawl touches ~760 pages. This layer keeps it sequential, slow and
resumable: responses land in a content-addressed disk cache so re-runs during
development never hit the network again.
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

USER_AGENT = (
    "psmf-cal/1.0 (static calendar generator for Hanspaulska liga; "
    "contact: https://www.psmf.cz/ webmaster via league)"
)
REQUEST_DELAY_SECONDS = 0.4
MAX_ATTEMPTS = 4
BACKOFF_BASE_SECONDS = 2.0
TIMEOUT_SECONDS = 30


class FetchError(RuntimeError):
    """A URL could not be retrieved after retries."""

    def __init__(self, url: str, detail: str) -> None:
        super().__init__(f"{url}: {detail}")
        self.url = url
        self.detail = detail


class CachedFetcher:
    """Sequential fetcher with an on-disk cache and retry-with-backoff.

    Only 5xx responses and transport errors are retried; a 404 is a structural
    problem with our URL building and must surface immediately.
    """

    def __init__(
        self,
        cache_dir: Path,
        *,
        use_cache: bool = True,
        delay: float = REQUEST_DELAY_SECONDS,
    ) -> None:
        self.cache_dir = cache_dir
        self.use_cache = use_cache
        self.delay = delay
        self.hits = 0
        self.misses = 0
        self._last_request_at = 0.0
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.html"

    def get(self, url: str) -> str:
        """Return the HTML for ``url``, from cache when possible."""
        path = self._cache_path(url)
        if self.use_cache and path.exists():
            self.hits += 1
            return path.read_text(encoding="utf-8")

        html = self._download(url)
        self.misses += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        return html

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_at = time.monotonic()

    def _download(self, url: str) -> str:
        last_detail = "no attempt made"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._throttle()
            try:
                response = self._session.get(url, timeout=TIMEOUT_SECONDS)
            except requests.RequestException as exc:
                last_detail = f"transport error: {exc}"
            else:
                if response.status_code < 500:
                    if not response.ok:
                        raise FetchError(url, f"HTTP {response.status_code}")
                    # psmf.cz serves UTF-8 but does not always say so in the header.
                    response.encoding = response.apparent_encoding or "utf-8"
                    return response.text
                last_detail = f"HTTP {response.status_code}"

            if attempt < MAX_ATTEMPTS:
                pause = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                log.warning("  %s (%s) -- retrying in %.0fs", url, last_detail, pause)
                time.sleep(pause)

        raise FetchError(url, f"{last_detail} after {MAX_ATTEMPTS} attempts")
