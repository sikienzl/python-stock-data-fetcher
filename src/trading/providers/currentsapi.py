from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

from ..core.exceptions import APIError
from ..core.utils import get_api_key


BASE_URL = "https://api.currentsapi.services/v1"
CURRRENTS_DAILY_LIMIT_DEFAULT = 250
CURRRENTS_USAGE_FILE = Path.home() / ".trading_currents_usage.json"


class CurrentsAPIClient:
    """Client for Currents News API."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or get_api_key("currents")

    def _daily_limit(self) -> int:
        return int(os.getenv("CURRENTS_DAILY_LIMIT", str(CURRRENTS_DAILY_LIMIT_DEFAULT)))

    def _usage_state(self) -> dict[str, int | str]:
        today = datetime.now(timezone.utc).date().isoformat()
        try:
            data = json.loads(CURRRENTS_USAGE_FILE.read_text(encoding="utf-8"))
            if data.get("date") == today:
                return data
        except Exception:
            pass
        return {"date": today, "count": 0}

    def _save_usage_state(self, data: dict[str, int | str]) -> None:
        CURRRENTS_USAGE_FILE.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def _check_and_consume_quota(self) -> None:
        data = self._usage_state()
        count = int(data.get("count", 0))
        if count >= self._daily_limit():
            raise APIError("Currents API daily limit reached")
        data["count"] = count + 1
        self._save_usage_state(data)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise APIError("Missing Currents API key")
        return {"Authorization": f"Bearer {self.api_key}"}

    def get_latest_news(self, language: str = "en", category: str | None = None, country: str | None = None, page_number: int = 1, page_size: int | None = None) -> dict:
        params: dict[str, object] = {"language": language, "page_number": page_number}
        if category:
            params["category"] = category
        if country:
            params["country"] = country
        if page_size is not None:
            params["page_size"] = page_size

        try:
            self._check_and_consume_quota()
            response = requests.get(f"{BASE_URL}/latest-news", headers=self._headers(), params=params, timeout=15)
            if response.status_code == 200:
                return response.json()
            if response.status_code == 429:
                raise APIError("Currents API quota exhausted")
            raise APIError(f"Currents API error: {response.status_code}")
        except Exception as exc:
            raise APIError(f"Currents API error: {str(exc)}")

    def search_news(self, keywords: str, language: str = "en", category: str | None = None, country: str | None = None, page_number: int = 1, page_size: int | None = None) -> dict:
        params: dict[str, object] = {"keywords": keywords, "language": language, "page_number": page_number}
        if category:
            params["category"] = category
        if country:
            params["country"] = country
        if page_size is not None:
            params["page_size"] = page_size

        try:
            self._check_and_consume_quota()
            response = requests.get(f"{BASE_URL}/search", headers=self._headers(), params=params, timeout=15)
            if response.status_code == 200:
                return response.json()
            if response.status_code == 429:
                raise APIError("Currents API quota exhausted")
            raise APIError(f"Currents API error: {response.status_code}")
        except Exception as exc:
            raise APIError(f"Currents API error: {str(exc)}")


def currents_news():
    """Legacy helper for Currents API news."""
    try:
        client = CurrentsAPIClient()
        return client.get_latest_news()
    except APIError as exc:
        print(f"Error: {exc}")
        return None