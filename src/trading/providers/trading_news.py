from .currentsapi import CurrentsAPIClient
from .finnhub_news import FinnhubNewsAPI
from .alphavantage import AlphaVantageClient
from ..core.exceptions import APIError

def fetch_trading_news(symbol: str = "AAPL") -> dict:
    """Fetch trading news from all configured providers."""
    print("Fetching trading news...")

    # Fetch from Finnhub
    print("🔹 Fetching from Finnhub...")
    try:
        finnhub_news = FinnhubNewsAPI().fetch_news(symbol=symbol)
        print(f"Finnhub news fetched: {len(finnhub_news)} items")
    except APIError as e:
        print(f"Finnhub error: {e}")
        finnhub_news = None

    # Fetch from Alpha Vantage
    print("🔹 Fetching from Alpha Vantage...")
    try:
        alpha_news = AlphaVantageClient().get_news_sentiment(symbol)
        print("Alpha Vantage news fetched")
    except APIError as e:
        print(f"Alpha Vantage error: {e}")
        alpha_news = None

    print("🔹 Fetching from Currents API...")
    try:
        currents_news = CurrentsAPIClient().search_news(keywords=symbol)
        print("Currents news fetched")
    except APIError as e:
        print(f"Currents error: {e}")
        currents_news = None

    return {
        "finnhub": finnhub_news,
        "alpha_vantage": alpha_news,
        "currents": currents_news,
    }