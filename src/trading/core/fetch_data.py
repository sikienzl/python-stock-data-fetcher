from .utils import get_api_key
from ..providers import FinnhubClient, AlphaVantageClient

def fetch_data(symbol: str, provider: str = "finnhub", **kwargs):
    """Fetch stock data from the specified provider."""
    api_key = get_api_key(provider)
    if provider == "finnhub":
        client = FinnhubClient(api_key)
        return client.get_quote(symbol, **kwargs)
    elif provider == "alpha_vantage":
        client = AlphaVantageClient(api_key)
        return client.get_quote(symbol, **kwargs)
    else:
        raise ValueError(f"Unsupported provider: {provider}")