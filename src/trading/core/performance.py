from __future__ import annotations

from math import sqrt

from .portfolio import list_positions


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


def portfolio_metrics(current_prices: dict[str, float], db_path: str | None = None) -> dict:
    positions = list_positions(db_path)
    total_cost = 0.0
    total_value = 0.0
    holdings = []

    for position in positions:
        position_id = position["id"]
        symbol = position["symbol"]
        quantity = float(position["quantity"])
        average_price = float(position["average_price"])
        current_price = float(current_prices.get(symbol, average_price))
        cost = quantity * average_price
        value = quantity * current_price
        total_cost += cost
        total_value += value
        holdings.append(
            {
                "id": position_id,
                "symbol": symbol,
                "quantity": quantity,
                "average_price": average_price,
                "current_price": current_price,
                "cost": cost,
                "value": value,
                "pnl": value - cost,
            }
        )

    total_return = (total_value / total_cost - 1) if total_cost else 0.0
    price_series = [entry["current_price"] for entry in holdings] if holdings else []

    return {
        "holdings": holdings,
        "total_cost": total_cost,
        "total_value": total_value,
        "total_pnl": total_value - total_cost,
        "roi": total_return,
        "sharpe_ratio": calculate_sharpe_ratio(price_series),
        "max_drawdown": calculate_max_drawdown(price_series),
    }