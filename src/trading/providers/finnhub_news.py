from ..core.utils import get_api_key
from ..core.exceptions import APIError

try:
    import finnhub
except ModuleNotFoundError:
    finnhub = None

class FinnhubNewsAPI:
    """Client for Finnhub.io News API."""

    def __init__(self):
        self.api_key = get_api_key("finnhub")
        if finnhub is None:
            self.client = None
            return
        self.client = finnhub.Client(api_key=self.api_key)

    def fetch_news(
        self,
        symbol: str | None = None,
        category: str = "general",
        min_id: int = 0
    ) -> list[dict]:
        """Fetch news from Finnhub."""
        if self.client is None:
            raise APIError("finnhub-python is not installed")
        try:
            if symbol:
                return self.client.company_news(
                    symbol,
                    _from="2020-01-01",
                    to="2025-01-01"
                )
            return self.client.general_news(category, min_id=min_id)
        except Exception as e:
            raise APIError(f"Finnhub News API error: {str(e)}")

    def fetch_country(self) -> dict:
        """Fetch country information."""
        if self.client is None:
            raise APIError("finnhub-python is not installed")
        try:
            return self.client.country()
        except Exception as e:
            raise APIError(f"Finnhub News API error: {str(e)}")

# Legacy function for backward compatibility
def finnhub_news():
    """Legacy function to fetch news (backward compatible)."""
    print("Fetching news from Finnhub...")
    try:
        api = FinnhubNewsAPI()
        news = api.fetch_country()
        print(news)
        return news
    except APIError as e:
        print(f"Error: {e}")
        return None