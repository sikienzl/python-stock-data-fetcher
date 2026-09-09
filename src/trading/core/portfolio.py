from __future__ import annotations

from pathlib import Path
import sqlite3


DEFAULT_PORTFOLIO_DB_PATH = Path.home() / ".trading_portfolio.sqlite3"


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db_path or DEFAULT_PORTFOLIO_DB_PATH))
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS portfolio_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            quantity REAL NOT NULL,
            average_price REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return connection


def add_position(symbol: str, quantity: float, average_price: float, db_path: str | Path | None = None) -> int:
    with _connect(db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO portfolio_positions (symbol, quantity, average_price) VALUES (?, ?, ?)",
            (symbol.upper(), quantity, average_price),
        )
        return int(cursor.lastrowid)


def list_positions(db_path: str | Path | None = None) -> list[dict]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT symbol, quantity, average_price, created_at FROM portfolio_positions ORDER BY created_at DESC"
        ).fetchall()

    return [
        {
            "symbol": row[0],
            "quantity": row[1],
            "average_price": row[2],
            "created_at": row[3],
        }
        for row in rows
    ]


def portfolio_value(current_prices: dict[str, float], db_path: str | Path | None = None) -> dict:
    positions = list_positions(db_path)
    holdings = []
    total_cost = 0.0
    total_value = 0.0

    for position in positions:
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
                "symbol": symbol,
                "quantity": quantity,
                "average_price": average_price,
                "current_price": current_price,
                "cost": cost,
                "value": value,
                "pnl": value - cost,
            }
        )

    return {
        "holdings": holdings,
        "total_cost": total_cost,
        "total_value": total_value,
        "total_pnl": total_value - total_cost,
    }