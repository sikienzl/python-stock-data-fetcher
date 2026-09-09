"""Finnhub market data provider."""

from __future__ import annotations

import json
import threading
from typing import Callable

from ..core.utils import get_api_key
from ..core.exceptions import APIError

try:
    import finnhub
except ModuleNotFoundError:
    finnhub = None

try:
    import websocket
except ModuleNotFoundError:
    websocket = None

FINNHUB_WEBSOCKET_URL = "wss://ws.finnhub.io?token={token}"

class FinnhubClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or get_api_key("finnhub")
        if finnhub is None:
            self.client = None
            return
        self.client = finnhub.Client(api_key=self.api_key)

    def get_quote(self, symbol: str) -> dict:
        if self.client is None:
            raise APIError("finnhub-python is not installed")
        try:
            return self.client.quote(symbol)
        except Exception as e:
            raise APIError(f"Finnhub API-Fehler: {str(e)}")

    def stream_quotes(
        self,
        symbol: str,
        callback: Callable[[dict], None],
        max_messages: int | None = None,
    ) -> None:
        if websocket is None:
            raise APIError("websocket-client is not installed")

        token = self.api_key
        if not token:
            raise APIError("Missing Finnhub API key")

        def on_open(ws):
            ws.send(json.dumps({"type": "subscribe", "symbol": symbol}))

        def on_message(_ws, message: str):
            payload = json.loads(message)
            for item in payload.get("data", []):
                callback(item)
                if max_messages is not None:
                    on_message.received += 1
                    if on_message.received >= max_messages:
                        ws.close()
                        return

        on_message.received = 0

        def on_error(_ws, error):
            raise APIError(f"Finnhub WebSocket error: {error}")

        def on_close(_ws, *_args):
            return None

        ws = websocket.WebSocketApp(
            FINNHUB_WEBSOCKET_URL.format(token=token),
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )

        try:
            ws.run_forever(ping_interval=30, ping_timeout=10)
        except KeyboardInterrupt:
            ws.close()
        except Exception as e:
            raise APIError(f"Finnhub WebSocket error: {str(e)}")