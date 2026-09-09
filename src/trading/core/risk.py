from __future__ import annotations


def calculate_position_size(
    account_size: float,
    risk_per_trade: float,
    entry_price: float,
    stop_loss_price: float,
) -> float:
    if account_size <= 0 or risk_per_trade <= 0:
        raise ValueError("account_size and risk_per_trade must be positive")
    if entry_price <= stop_loss_price:
        raise ValueError("entry_price must be greater than stop_loss_price")

    risk_amount = account_size * risk_per_trade
    risk_per_share = entry_price - stop_loss_price
    return risk_amount / risk_per_share


def calculate_stop_loss(entry_price: float, stop_loss_percent: float = 0.05) -> float:
    if entry_price <= 0:
        raise ValueError("entry_price must be positive")
    if not 0 < stop_loss_percent < 1:
        raise ValueError("stop_loss_percent must be between 0 and 1")
    return entry_price * (1 - stop_loss_percent)