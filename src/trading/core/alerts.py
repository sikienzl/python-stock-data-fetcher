from __future__ import annotations

from pathlib import Path
import sqlite3


DEFAULT_ALERTS_DB_PATH = Path.home() / ".trading_alerts.sqlite3"


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db_path or DEFAULT_ALERTS_DB_PATH))
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS price_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            operator TEXT NOT NULL,
            target_price REAL NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            triggered_at TIMESTAMP
        )
        """
    )
    return connection


def create_price_alert(
    symbol: str,
    operator: str,
    target_price: float,
    db_path: str | Path | None = None,
) -> int:
    if operator not in {">", "<", ">=", "<="}:
        raise ValueError("operator must be one of >, <, >=, <=")

    with _connect(db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO price_alerts (symbol, operator, target_price) VALUES (?, ?, ?)",
            (symbol.upper(), operator, target_price),
        )
        return int(cursor.lastrowid)


def list_price_alerts(db_path: str | Path | None = None) -> list[dict]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT id, symbol, operator, target_price, active, created_at, triggered_at FROM price_alerts ORDER BY created_at DESC"
        ).fetchall()

    return [
        {
            "id": row[0],
            "symbol": row[1],
            "operator": row[2],
            "target_price": row[3],
            "active": bool(row[4]),
            "created_at": row[5],
            "triggered_at": row[6],
        }
        for row in rows
    ]


def evaluate_price_alerts(symbol: str, current_price: float, db_path: str | Path | None = None) -> list[dict]:
    symbol = symbol.upper()
    triggered: list[dict] = []

    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT id, operator, target_price FROM price_alerts WHERE symbol = ? AND active = 1",
            (symbol,),
        ).fetchall()

        for alert_id, operator, target_price in rows:
            matched = (
                operator == ">" and current_price > target_price
                or operator == "<" and current_price < target_price
                or operator == ">=" and current_price >= target_price
                or operator == "<=" and current_price <= target_price
            )
            if matched:
                connection.execute(
                    "UPDATE price_alerts SET active = 0, triggered_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (alert_id,),
                )
                triggered.append(
                    {
                        "id": alert_id,
                        "symbol": symbol,
                        "operator": operator,
                        "target_price": target_price,
                        "current_price": current_price,
                    }
                )

    return triggered