from ..core.utils import get_api_key
import requests
from ..core.exceptions import APIError

BASE_URL_ALPHAVANTAGE = "https://www.alphavantage.co/query?"

class AlphaVantageClient:
    """Client for Alpha Vantage API."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or get_api_key("alpha_vantage")

    def get_news_sentiment(self, symbol: str) -> dict:
        """Fetch news sentiment for a given symbol."""
        try:
            url = f"{BASE_URL_ALPHAVANTAGE}function=NEWS_SENTIMENT&symbol={symbol}&apikey={self.api_key}"
            response = requests.get(url)
            if response.status_code == 200:
                return response.json()
            else:
                raise APIError(f"Alpha Vantage API error: {response.status_code}")
        except Exception as e:
            raise APIError(f"Alpha Vantage API error: {str(e)}")

    def get_quote(self, symbol: str) -> dict:
        """Fetch stock quote for a given symbol."""
        try:
            url = f"{BASE_URL_ALPHAVANTAGE}function=GLOBAL_QUOTE&symbol={symbol}&apikey={self.api_key}"
            response = requests.get(url)
            if response.status_code == 200:
                return response.json()
            else:
                raise APIError(f"Alpha Vantage API error: {response.status_code}")
        except Exception as e:
            raise APIError(f"Alpha Vantage API error: {str(e)}")

# Legacy function for backward compatibility
def alphavantage():
    """Legacy function to fetch news (backward compatible)."""
    print("Fetching news from Alpha Vantage...")
    try:
        client = AlphaVantageClient()
        news = client.get_news_sentiment("AAPL")
        print(news)
        return news
    except APIError as e:
        print(f"Error: {e}")
        return None