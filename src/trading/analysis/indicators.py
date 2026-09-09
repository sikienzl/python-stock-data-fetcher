from __future__ import annotations

from math import isnan


def _validate_prices(prices: list[float], period: int) -> None:
    if period <= 0:
        raise ValueError("period must be greater than zero")
    if len(prices) < period:
        raise ValueError("not enough prices for the requested period")


def calculate_sma(prices: list[float], period: int) -> float:
    _validate_prices(prices, period)
    return sum(prices[-period:]) / period


def calculate_ema(prices: list[float], period: int) -> float:
    _validate_prices(prices, period)
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = ((price - ema) * multiplier) + ema
    return ema


def calculate_rsi(prices: list[float], period: int = 14) -> float:
    _validate_prices(prices, period + 1)

    gains: list[float] = []
    losses: list[float] = []
    recent_prices = prices[-(period + 1):]
    for previous, current in zip(recent_prices, recent_prices[1:]):
        delta = current - previous
        gains.append(max(delta, 0.0))
        losses.append(abs(min(delta, 0.0)))

    average_gain = sum(gains) / period
    average_loss = sum(losses) / period

    if average_loss == 0:
        return 100.0

    rs = average_gain / average_loss
    rsi = 100 - (100 / (1 + rs))
    return 0.0 if isnan(rsi) else rsi


def calculate_macd(
    prices: list[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> dict[str, float]:
    if fast_period <= 0 or slow_period <= 0 or signal_period <= 0:
        raise ValueError("periods must be greater than zero")
    if fast_period >= slow_period:
        raise ValueError("fast_period must be smaller than slow_period")
    if len(prices) < slow_period + 1:
        raise ValueError("not enough prices for MACD calculation")

    macd_values: list[float] = []
    for index in range(slow_period, len(prices) + 1):
        fast_ema = calculate_ema(prices[:index], fast_period)
        slow_ema = calculate_ema(prices[:index], slow_period)
        macd_values.append(fast_ema - slow_ema)

    effective_signal_period = min(signal_period, len(macd_values))
    signal_line = calculate_ema(macd_values, effective_signal_period)
    macd_line = macd_values[-1]

    return {
        "macd": macd_line,
        "signal": signal_line,
        "histogram": macd_line - signal_line,
    }