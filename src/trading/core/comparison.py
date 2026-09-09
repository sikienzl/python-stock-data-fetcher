from __future__ import annotations

from .fetch_data import fetch_data


def compare_providers(symbol: str, providers: list[str] | None = None) -> dict:
    providers = providers or ["finnhub", "alpha_vantage"]
    results: dict[str, dict] = {}

    for provider in providers:
        try:
            results[provider] = fetch_data(symbol, provider=provider, save_to_db=False)
        except Exception as error:
            results[provider] = {"error": str(error)}

    return {
        "symbol": symbol.upper(),
        "results": results,
    }