# trading/providers/finnhub.py
from ..core.utils import get_api_key
from ..core.exceptions import APIError

try:
    import finnhub
except ModuleNotFoundError:
    finnhub = None

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