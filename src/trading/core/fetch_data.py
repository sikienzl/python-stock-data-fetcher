from .utils import get_api_key
from .rate_limit import wait_for_provider_interval
from .storage import save_quote
from ..providers import FinnhubClient, AlphaVantageClient
from ..analysis.indicators import calculate_ema, calculate_macd, calculate_rsi, calculate_sma

def fetch_data(symbol: str, provider: str = "finnhub", save_to_db: bool = True, **kwargs):
    """Fetch stock data from the specified provider."""
    api_key = get_api_key(provider)
    wait_for_provider_interval(provider)
    if provider == "finnhub":
        client = FinnhubClient(api_key)
        quote = client.get_quote(symbol, **kwargs)
    elif provider == "alpha_vantage":
        client = AlphaVantageClient(api_key)
        quote = client.get_quote(symbol, **kwargs)
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    if save_to_db:
        save_quote(symbol, provider, quote)

    return quote


def analyze_prices(prices: list[float], period: int = 14) -> dict[str, float | dict[str, float]]:
    """Calculate the most common technical indicators for a price series."""
    return {
        "sma": calculate_sma(prices, period),
        "ema": calculate_ema(prices, period),
        "rsi": calculate_rsi(prices, period),
        "macd": calculate_macd(prices),
    }