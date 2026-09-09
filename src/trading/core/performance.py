from __future__ import annotations

import contextlib
import json
from math import sqrt
from urllib.parse import quote_plus

import requests

from .portfolio import list_positions
from .storage import load_quotes


ING_SYMBOL_ALIASES: dict[str, list[str]] = {
    "590900": ["Bilfinger", "Bilfinger SE", "GBF"],
    "840400": ["Allianz", "ALV.DE", "ALV"],
    "555750": ["Deutsche Telekom", "DTE.DE", "DTE"],
    "ENAG99": ["E.ON", "EOAN.DE", "EOAN"],
    "543900": ["Continental", "CON.DE", "CON"],
    "BASF11": ["BASF", "BAS.DE", "BAS"],
    "519000": ["BMW", "BMW.DE", "BMW"],
    "A0WMPJ": ["Aixtron", "AIXA.DE", "AIXA"],
    "RENK73": ["RENK", "RENK.DE", "RENK.F"],
}


def _positive_float(value: object) -> float | None:
    try:
        numeric_value = float(value)
    except Exception:
        return None
    return numeric_value if numeric_value > 0 else None


def _latest_quote_prices(db_path: str | None = None) -> dict[str, float]:
    prices: dict[str, float] = {}
    for quote in load_quotes(db_path=db_path):
        if not isinstance(quote, dict):
            continue
        symbol = str(quote.get("symbol") or "").upper()
        payload = quote.get("payload") if isinstance(quote.get("payload"), dict) else None
        if not symbol or symbol in prices or not isinstance(payload, dict):
            continue
        value = payload.get("c") if payload.get("c") not in (None, 0) else payload.get("price")
        numeric_value = _positive_float(value)
        if numeric_value is not None:
            prices[symbol] = numeric_value
    return prices


def _yahoo_candidates(symbol: str, name: str | None = None) -> list[str]:
    candidates: list[str] = []
    normalized_symbol = symbol.strip().upper()
    if normalized_symbol:
        candidates.append(normalized_symbol)
        candidates.extend(ING_SYMBOL_ALIASES.get(normalized_symbol, []))
        stripped_symbol = normalized_symbol.rstrip("0123456789")
        if stripped_symbol and stripped_symbol != normalized_symbol:
            candidates.append(stripped_symbol)
    if name:
        normalized_name = name.strip()
        if normalized_name:
            candidates.append(normalized_name)
    return candidates


def _yahoo_quote_price(symbol: str, name: str | None = None) -> float | None:
    headers = {"User-Agent": "Mozilla/5.0"}
    for candidate in _yahoo_candidates(symbol, name):
        search_url = f"https://query1.finance.yahoo.com/v1/finance/search?q={quote_plus(candidate)}"
        try:
            response = requests.get(search_url, headers=headers, timeout=10)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            continue

        for quote in payload.get("quotes", []) if isinstance(payload, dict) else []:
            if not isinstance(quote, dict):
                continue
            quote_symbol = str(quote.get("symbol") or "").strip().upper()
            quote_name = str(quote.get("shortname") or quote.get("longname") or "")
            if not quote_symbol:
                continue
            if candidate.upper() not in {quote_symbol, quote_name.upper()} and candidate.lower() not in quote_name.lower():
                continue
            chart_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote_symbol}"
            try:
                chart_response = requests.get(chart_url, headers=headers, timeout=10)
                chart_response.raise_for_status()
                chart_payload = chart_response.json()
                result = chart_payload.get("chart", {}).get("result", [])
                if not result:
                    continue
                meta = result[0].get("meta", {}) if isinstance(result[0], dict) else {}
                price = meta.get("regularMarketPrice") or meta.get("previousClose")
                numeric_price = _positive_float(price)
                if numeric_price is not None:
                    return numeric_price
            except Exception:
                continue
    return None


def calculate_returns(prices: list[float]) -> list[float]:
    if len(prices) < 2:
        return []

    returns: list[float] = []
    for previous, current in zip(prices, prices[1:]):
        if previous == 0:
            continue
        returns.append((current / previous) - 1)
    return returns


def calculate_sharpe_ratio(prices: list[float], risk_free_rate: float = 0.0) -> float:
    returns = calculate_returns(prices)
    if not returns:
        return 0.0
    excess_returns = [value - risk_free_rate for value in returns]
    mean_return = sum(excess_returns) / len(excess_returns)
    variance = sum((value - mean_return) ** 2 for value in excess_returns) / len(excess_returns)
    if variance == 0:
        return 0.0
    return mean_return / sqrt(variance) * sqrt(len(excess_returns))


def calculate_max_drawdown(prices: list[float]) -> float:
    if not prices:
        return 0.0

    non_zero_prices = [price for price in prices if price > 0]
    if not non_zero_prices:
        return 0.0

    peak = non_zero_prices[0]
    max_drawdown = 0.0
    for price in non_zero_prices:
        peak = max(peak, price)
        if peak == 0:
            continue
        drawdown = (price - peak) / peak
        max_drawdown = min(max_drawdown, drawdown)
    return max_drawdown


def portfolio_metrics(
    current_prices: dict[str, float],
    db_path: str | None = None,
    allow_remote_price_lookup: bool = True,
) -> dict:
    positions = list_positions(db_path)
    latest_prices = _latest_quote_prices(db_path)
    total_cost = 0.0
    total_value = 0.0
    holdings = []
    missing_price_symbols: list[str] = []

    for position in positions:
        position_id = position["id"]
        symbol = position["symbol"]
        quantity = float(position["quantity"])
        average_price = float(position["average_price"])
        name = position.get("name")
        current_price = _positive_float(current_prices.get(symbol))
        price_source = "live"
        if current_price is None:
            current_price = _positive_float(latest_prices.get(symbol))
            price_source = "stored_quote"
        if current_price is None and allow_remote_price_lookup:
            current_price = _yahoo_quote_price(symbol, name)
            if current_price is not None:
                price_source = "yahoo_finance"
        if current_price is None:
            price_source = "missing"
            missing_price_symbols.append(symbol)
        cost = quantity * average_price
        value = quantity * current_price if current_price is not None else None
        pnl = (value - cost) if value is not None else None
        pnl_percent = (pnl / cost) if (pnl is not None and cost) else None
        total_cost += cost
        total_value += value if value is not None else 0.0
        holdings.append(
            {
                "id": position_id,
                "symbol": symbol,
                "quantity": quantity,
                "average_price": average_price,
                "current_price": current_price,
                "price_source": price_source,
                "cost": cost,
                "value": value,
                "pnl": pnl,
                "pnl_percent": pnl_percent,
            }
        )

    total_return = (total_value / total_cost - 1) if total_cost else 0.0
    price_series = [entry["current_price"] for entry in holdings if entry["current_price"] is not None] if holdings else []

    return {
        "holdings": holdings,
        "total_cost": total_cost,
        "total_value": total_value,
        "total_pnl": total_value - total_cost,
        "roi": total_return,
        "sharpe_ratio": calculate_sharpe_ratio(price_series),
        "max_drawdown": calculate_max_drawdown(price_series),
        "missing_price_symbols": missing_price_symbols,
    }


def portfolio_risk_snapshot(holdings: list[dict], current_prices: dict[str, float] | None = None) -> dict:
    current_prices = current_prices or {}
    analyzed_holdings: list[dict] = []
    total_value = 0.0
    total_cost = 0.0
    missing_price_symbols: list[str] = []

    for holding in holdings:
        symbol = str(holding.get("symbol", "")).upper()
        quantity = float(holding.get("quantity", 0.0))
        average_price = float(holding.get("average_price", 0.0))
        current_price = _positive_float(current_prices.get(symbol))
        if current_price is None:
            if symbol and symbol not in missing_price_symbols:
                missing_price_symbols.append(symbol)
        cost = quantity * average_price
        value = quantity * current_price if current_price is not None else None
        pnl = (value - cost) if value is not None else None
        pnl_percent = (pnl / cost) if (pnl is not None and cost) else None
        total_cost += cost
        total_value += value if value is not None else 0.0
        analyzed_holdings.append(
            {
                "symbol": symbol,
                "quantity": quantity,
                "average_price": average_price,
                "current_price": current_price,
                "cost": cost,
                "value": value,
                "pnl": pnl,
                "pnl_percent": pnl_percent,
                "weight": 0.0,
            }
        )

    if total_value > 0:
        for holding in analyzed_holdings:
            holding["weight"] = holding["value"] / total_value

    winners = sum(1 for holding in analyzed_holdings if holding["pnl"] is not None and holding["pnl"] > 0)
    losers = sum(1 for holding in analyzed_holdings if holding["pnl"] is not None and holding["pnl"] < 0)
    largest_position = max((holding["weight"] for holding in analyzed_holdings), default=0.0)
    top_weighted = sorted(analyzed_holdings, key=lambda item: item["weight"], reverse=True)[:3]
    priced_holdings = [holding for holding in analyzed_holdings if holding["pnl"] is not None]
    top_winners = sorted(priced_holdings, key=lambda item: item["pnl"], reverse=True)[:3]
    top_losers = sorted(priced_holdings, key=lambda item: item["pnl"])[:3]

    concentration_risk = "low"
    if largest_position >= 0.5:
        concentration_risk = "high"
    elif largest_position >= 0.3:
        concentration_risk = "medium"

    return {
        "position_count": len(analyzed_holdings),
        "total_cost": total_cost,
        "total_value": total_value,
        "total_pnl": total_value - total_cost,
        "roi": ((total_value / total_cost) - 1) if total_cost else 0.0,
        "winners": winners,
        "losers": losers,
        "largest_position_weight": largest_position,
        "concentration_risk": concentration_risk,
        "top_weighted": top_weighted,
        "top_winners": top_winners,
        "top_losers": top_losers,
        "missing_price_symbols": missing_price_symbols,
    }