from __future__ import annotations

from .backtesting import moving_average_crossover_backtest
from ..analysis.indicators import calculate_rsi, calculate_sma


def backtest_sma_crossover(prices: list[float], fast_period: int = 20, slow_period: int = 50) -> dict:
    return moving_average_crossover_backtest(prices, fast_period=fast_period, slow_period=slow_period)


def backtest_rsi_strategy(prices: list[float], period: int = 14, oversold: float = 30.0, overbought: float = 70.0) -> dict:
    if len(prices) <= period:
        raise ValueError("not enough prices for RSI backtest")
    signals: list[dict] = []
    for index in range(period + 1, len(prices) + 1):
        current_rsi = calculate_rsi(prices[:index], period=period)
        current_price = prices[index - 1]
        if current_rsi < oversold:
            signals.append({"action": "buy", "price": current_price, "index": index - 1, "rsi": current_rsi})
        elif current_rsi > overbought:
            signals.append({"action": "sell", "price": current_price, "index": index - 1, "rsi": current_rsi})
    return {"strategy": "rsi", "signals": signals, "total_signals": len(signals)}


def compare_strategies(prices: list[float]) -> dict:
    return {
        "sma_crossover": backtest_sma_crossover(prices),
        "rsi": backtest_rsi_strategy(prices),
    }