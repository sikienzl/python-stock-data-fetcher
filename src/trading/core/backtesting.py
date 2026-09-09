from __future__ import annotations


def moving_average_crossover_backtest(
    prices: list[float],
    fast_period: int = 5,
    slow_period: int = 20,
) -> dict:
    if fast_period <= 0 or slow_period <= 0:
        raise ValueError("periods must be greater than zero")
    if fast_period >= slow_period:
        raise ValueError("fast_period must be smaller than slow_period")
    if len(prices) < slow_period:
        raise ValueError("not enough prices for backtesting")

    position = 0
    entry_price = 0.0
    trades: list[dict] = []

    def sma(values: list[float]) -> float:
        return sum(values) / len(values)

    for index in range(slow_period, len(prices) + 1):
        window = prices[:index]
        fast_value = sma(window[-fast_period:])
        slow_value = sma(window[-slow_period:])
        price = window[-1]

        if fast_value > slow_value and position == 0:
            position = 1
            entry_price = price
            trades.append({"action": "buy", "price": price, "index": index - 1})
        elif fast_value < slow_value and position == 1:
            position = 0
            trades.append({"action": "sell", "price": price, "index": index - 1, "pnl": price - entry_price})

    realized_pnl = sum(trade.get("pnl", 0.0) for trade in trades)
    return {
        "strategy": "moving_average_crossover",
        "fast_period": fast_period,
        "slow_period": slow_period,
        "trades": trades,
        "total_trades": len(trades),
        "realized_pnl": realized_pnl,
    }