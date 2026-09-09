# trading/providers/__init__.py
from .finnhub import FinnhubClient
from .alphavantage import AlphaVantageClient
from .currentsapi import CurrentsAPIClient, currents_news as fetch_currents_news
from .finnhub_news import finnhub_news as fetch_finnhub_news
from .trading_news import fetch_trading_news

# Backward compatibility for older imports and cached bytecode.
FinhubClient = FinnhubClient

__all__ = [
    "FinnhubClient",
    "FinhubClient",
    "AlphaVantageClient",
    "CurrentsAPIClient",
    "fetch_finnhub_news",
    "fetch_currents_news",
    "fetch_trading_news",
]