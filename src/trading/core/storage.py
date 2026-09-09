from __future__ import annotations

import json
import sqlite3
from pathlib import Path


DEFAULT_DB_PATH = Path.home() / ".trading_stock_data.sqlite3"


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db_path or DEFAULT_DB_PATH))
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            provider TEXT NOT NULL,
            payload TEXT NOT NULL,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return connection


def save_quote(
    symbol: str,
    provider: str,
    payload: dict,
    db_path: str | Path | None = None,
) -> None:
    with _connect(db_path) as connection:
        connection.execute(
            "INSERT INTO stock_quotes (symbol, provider, payload) VALUES (?, ?, ?)",
            (symbol, provider, json.dumps(payload)),
        )


def load_quotes(
    symbol: str | None = None,
    provider: str | None = None,
    db_path: str | Path | None = None,
) -> list[dict]:
    query = "SELECT symbol, provider, payload, fetched_at FROM stock_quotes"
    conditions: list[str] = []
    parameters: list[str] = []

    if symbol:
        conditions.append("symbol = ?")
        parameters.append(symbol)
    if provider:
        conditions.append("provider = ?")
        parameters.append(provider)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY fetched_at DESC"

    with _connect(db_path) as connection:
        rows = connection.execute(query, parameters).fetchall()

    return [
        {
            "symbol": row[0],
            "provider": row[1],
            "payload": json.loads(row[2]),
            "fetched_at": row[3],
        }
        for row in rows
    ]