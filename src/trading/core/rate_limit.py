from __future__ import annotations

import os
import threading
import time


_LOCK = threading.Lock()
_LAST_REQUEST_AT: dict[str, float] = {}


def _default_interval(provider: str) -> float:
    if provider == "finnhub":
        return float(os.getenv("FINNHUB_MIN_INTERVAL_SECONDS", "1.0"))
    if provider == "alpha_vantage":
        return float(os.getenv("ALPHA_VANTAGE_MIN_INTERVAL_SECONDS", "15.0"))
    if provider == "currents":
        return float(os.getenv("CURRENTS_MIN_INTERVAL_SECONDS", "1.0"))
    return 0.0


def wait_for_provider_interval(provider: str, interval_seconds: float | None = None) -> None:
    minimum_interval = _default_interval(provider) if interval_seconds is None else interval_seconds
    if minimum_interval <= 0:
        return

    with _LOCK:
        now = time.monotonic()
        last_request_at = _LAST_REQUEST_AT.get(provider)
        if last_request_at is not None:
            elapsed = now - last_request_at
            if elapsed < minimum_interval:
                time.sleep(minimum_interval - elapsed)
        _LAST_REQUEST_AT[provider] = time.monotonic()


def get_provider_min_interval(provider: str) -> float:
    return _default_interval(provider)