"""Paced, retrying client for Kalshi's public (no-auth) market-data API.

Ground truth for endpoint behavior: docs/kalshi-api-notes.md
Kalshi sends no Retry-After header on 429; backoff is blind exponential.
"""
from __future__ import annotations

import random
import sys
import threading
import time
from collections.abc import Iterator

import httpx

DEFAULT_BASE = "https://api.elections.kalshi.com/trade-api/v2"


class KalshiApiError(Exception):
    pass


class KalshiClient:
    """Thread-safe: one instance may be shared by many shard walkers.

    Pacing is a global min-interval across all threads (the exchange budget
    is per account/IP, not per cursor); the actual HTTP round-trips overlap.
    """

    def __init__(self, base_url: str = DEFAULT_BASE, rps: float = 8.0,
                 timeout: float = 30.0, transport: httpx.BaseTransport | None = None,
                 max_retries: int = 10):
        self.rps = rps
        self.max_retries = max_retries
        self._min_interval = 1.0 / rps
        self._last_request = 0.0
        self._pace_lock = threading.Lock()
        self._client = httpx.Client(
            base_url=base_url, timeout=timeout, transport=transport,
            headers={"User-Agent": "kalshi-flb-research/0.1 (read-only)"},
        )

    def _pace(self) -> None:
        while True:
            with self._pace_lock:
                wait = self._min_interval - (time.monotonic() - self._last_request)
                if wait <= 0:
                    self._last_request = time.monotonic()
                    return
            time.sleep(wait)

    def _backoff(self, attempt: int) -> None:
        time.sleep(min(60.0, 2.0 ** attempt) + random.random())

    def get(self, path: str, params: dict | None = None) -> dict:
        for attempt in range(self.max_retries):
            self._pace()
            try:
                r = self._client.get(path, params=params)
            except httpx.TransportError:
                self._backoff(attempt)
                continue
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429 or r.status_code >= 500:
                if attempt >= 2:  # log persistent trouble, not routine blips
                    print(f"[api] {r.status_code} on {path} "
                          f"(attempt {attempt + 1}/{self.max_retries})",
                          file=sys.stderr, flush=True)
                self._backoff(attempt)
                continue
            raise KalshiApiError(f"{r.status_code} {path}: {r.text[:200]}")
        raise KalshiApiError(f"retries exhausted: {path}")

    def paginate(self, path: str, list_key: str, params: dict | None = None,
                 cursor: str | None = None, limit: int = 1000,
                 max_empty_pages: int = 5) -> Iterator[tuple[list[dict], str]]:
        """Yield (records, next_cursor) per page until the cursor runs dry.

        Pass a persisted `cursor` to resume mid-stream. An empty page with a
        non-empty cursor is NOT treated as the end (that would truncate the
        stream silently) — we keep walking through up to `max_empty_pages`
        consecutive empties, then raise so the caller can see it.
        """
        empties = 0
        while True:
            q = dict(params or {})
            q["limit"] = limit
            if cursor:
                q["cursor"] = cursor
            data = self.get(path, params=q)
            records = data.get(list_key) or []
            cursor = data.get("cursor") or ""
            yield records, cursor
            if not cursor:
                return
            empties = 0 if records else empties + 1
            if empties >= max_empty_pages:
                raise KalshiApiError(
                    f"{path}: {empties} consecutive empty pages with live cursor")
