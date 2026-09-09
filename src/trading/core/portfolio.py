from __future__ import annotations

import csv
import re
import subprocess
import tempfile
from pathlib import Path
import sqlite3
from typing import Iterable


DEFAULT_PORTFOLIO_DB_PATH = Path.home() / ".trading_portfolio.sqlite3"


def _normalize_source(source: str | None) -> str:
    return str(source or "manual").strip().lower() or "manual"


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db_path or DEFAULT_PORTFOLIO_DB_PATH))
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS portfolio_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL DEFAULT 'manual',
            name TEXT,
            symbol TEXT NOT NULL,
            quantity REAL NOT NULL,
            average_price REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    try:
        connection.execute("ALTER TABLE portfolio_positions ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'")
    except sqlite3.OperationalError:
        pass
    try:
        connection.execute("ALTER TABLE portfolio_positions ADD COLUMN name TEXT")
    except sqlite3.OperationalError:
        pass

    connection.execute(
        "UPDATE portfolio_positions SET source = LOWER(TRIM(source)) WHERE source IS NOT NULL AND source != LOWER(TRIM(source))"
    )
    return connection


def add_position(
    symbol: str,
    quantity: float,
    average_price: float,
    db_path: str | Path | None = None,
    source: str = "manual",
    name: str | None = None,
) -> int:
    normalized_source = _normalize_source(source)
    with _connect(db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO portfolio_positions (source, name, symbol, quantity, average_price) VALUES (?, ?, ?, ?, ?)",
            (normalized_source, name, symbol.upper(), quantity, average_price),
        )
        return int(cursor.lastrowid)


def update_position(
    position_id: int,
    symbol: str,
    quantity: float,
    average_price: float,
    source: str = "manual",
    name: str | None = None,
    db_path: str | Path | None = None,
) -> None:
    normalized_source = _normalize_source(source)
    with _connect(db_path) as connection:
        connection.execute(
            "UPDATE portfolio_positions SET source = ?, name = ?, symbol = ?, quantity = ?, average_price = ? WHERE id = ?",
            (normalized_source, name, symbol.upper(), quantity, average_price, position_id),
        )


def delete_position(position_id: int, db_path: str | Path | None = None) -> None:
    with _connect(db_path) as connection:
        connection.execute("DELETE FROM portfolio_positions WHERE id = ?", (position_id,))


def delete_all_positions(db_path: str | Path | None = None) -> None:
    with _connect(db_path) as connection:
        connection.execute("DELETE FROM portfolio_positions")


def delete_positions_by_source(source: str, db_path: str | Path | None = None) -> None:
    normalized_source = _normalize_source(source)
    with _connect(db_path) as connection:
        connection.execute("DELETE FROM portfolio_positions WHERE source = ?", (normalized_source,))


def _read_csv_rows(file_path: str | Path) -> tuple[list[dict[str, str]], str]:
    path = Path(file_path)
    encodings = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
    raw_text = None
    used_encoding = "utf-8-sig"

    for encoding in encodings:
        try:
            raw_text = path.read_text(encoding=encoding)
            used_encoding = encoding
            break
        except UnicodeDecodeError:
            continue

    if raw_text is None:
        raise ValueError(f"Could not decode CSV file: {path}")

    sample = raw_text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=[";", ",", "\t", "|"])
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";" if sample.count(";") >= sample.count(",") else ","

    reader = csv.DictReader(raw_text.splitlines(), delimiter=delimiter)
    rows = [dict(row) for row in reader]
    return rows, used_encoding


def _read_pdf_text(file_path: str | Path) -> str:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(path)

    with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False, encoding="utf-8") as tmp:
        output_path = Path(tmp.name)

    try:
        subprocess.run([
            "pdftotext",
            "-layout",
            str(path),
            str(output_path),
        ], check=True, capture_output=True)
        return output_path.read_text(encoding="utf-8", errors="replace")
    finally:
        output_path.unlink(missing_ok=True)


def _parse_quantity(value: str) -> float:
    return float(value.replace(".", "").replace(",", "."))


def _normalize_pdf_name(name: str | None) -> str | None:
    if not name:
        return None

    cleaned = re.sub(r"\s+", " ", name).strip()
    cleaned = re.sub(r"\b([A-Za-z]{3,})\s+([a-z])\b", r"\1\2", cleaned)
    cleaned = re.sub(r"\b([A-Za-z]{5,})\s+([a-z])\b", r"\1\2", cleaned)
    return cleaned or None


def _parse_ing_pdf_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    isin_pattern = re.compile(r"\b([A-Z]{2}[A-Z0-9]{10})\b")
    row_start_pattern = re.compile(r"^(?P<name>.*?)\s+(?P<symbol>[A-Z0-9]{4,12})\s+(?P<isin>[A-Z]{2}[A-Z0-9]{10})\s+(?P<quantity>[\d.,]+)\s+(?P<price>[\d.,]+)")

    pending_name_parts: list[str] = []

    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            continue
        if "ISIN" in line or line.startswith(("Tabelle", "Seite", "Kaufpreis", "Gesamtpreis", "Name", "Fonds", "ETFs", "Aktien")):
            pending_name_parts.clear()
            continue

        row_match = row_start_pattern.search(line)
        if row_match:
            name = row_match.group("name").strip() or None
            symbol = row_match.group("symbol").upper()
            isin = row_match.group("isin")
            quantity_text = row_match.group("quantity")
            avg_price_text = row_match.group("price")

            if pending_name_parts:
                buffered_name = " ".join(pending_name_parts).strip()
                if buffered_name:
                    name = f"{buffered_name} {name}".strip() if name else buffered_name
            pending_name_parts.clear()

            if name and name.upper() == symbol:
                name = None
            if name:
                name = _normalize_pdf_name(name)

            key = (symbol, isin)
            if key in seen:
                continue
            seen.add(key)

            rows.append(
                {
                    "name": _normalize_pdf_name(name),
                    "symbol": symbol,
                    "quantity": quantity_text,
                    "average_price": avg_price_text,
                    "isin": isin,
                }
            )
            continue

        if re.search(r"[A-Za-zÄÖÜäöüß]", line) and not re.search(r"\d", line):
            pending_name_parts.append(line)

    return rows


def _find_column(row: dict[str, str], candidates: Iterable[str]) -> str | None:
    normalized = {key.strip().lower().replace(" ", "_"): key for key in row}
    for candidate in candidates:
        key = normalized.get(candidate)
        if key:
            return key
    return None


def import_positions_from_csv(
    file_path: str | Path,
    db_path: str | Path | None = None,
    replace: bool = False,
    source: str = "manual",
) -> dict[str, int | str]:
    source = _normalize_source(source)
    rows, encoding = _read_csv_rows(file_path)
    imported = 0
    skipped = 0

    if replace:
        delete_positions_by_source(source, db_path)

    for row in rows:
        symbol_column = _find_column(row, ("symbol", "ticker", "isin"))
        quantity_column = _find_column(row, ("quantity", "pieces", "units", "amount", "shares"))
        price_column = _find_column(row, ("average_price", "avg_price", "purchase_price", "price", "entry_price"))

        if not symbol_column or not quantity_column or not price_column:
            skipped += 1
            continue

        symbol = str(row[symbol_column]).strip().upper()
        quantity_text = str(row[quantity_column]).strip().replace(",", ".")
        price_text = str(row[price_column]).strip().replace(",", ".")

        if not symbol:
            skipped += 1
            continue

        try:
            quantity = float(quantity_text)
            average_price = float(price_text)
        except ValueError:
            skipped += 1
            continue

        add_position(symbol, quantity, average_price, db_path=db_path, source=source)
        imported += 1

    return {
        "imported": imported,
        "skipped": skipped,
        "encoding": encoding,
        "rows": len(rows),
    }


def import_positions_from_pdf(
    file_path: str | Path,
    db_path: str | Path | None = None,
    replace: bool = False,
    source: str = "manual",
) -> dict[str, int | str]:
    source = _normalize_source(source)
    text = _read_pdf_text(file_path)
    rows = _parse_ing_pdf_rows(text)
    imported = 0
    skipped = 0

    if replace:
        delete_positions_by_source(source, db_path)

    for row in rows:
        symbol = row["symbol"].strip().upper()
        if not symbol:
            skipped += 1
            continue

        try:
            quantity = _parse_quantity(row["quantity"])
            average_price = _parse_quantity(row["average_price"])
        except ValueError:
            skipped += 1
            continue

        add_position(symbol, quantity, average_price, db_path=db_path, source=source, name=row.get("name"))
        imported += 1

    return {
        "imported": imported,
        "skipped": skipped,
        "rows": len(rows),
        "format": "pdf",
    }


def list_positions(db_path: str | Path | None = None) -> list[dict]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT id, source, name, symbol, quantity, average_price, created_at FROM portfolio_positions ORDER BY created_at DESC"
        ).fetchall()

    return [
        {
            "id": row[0],
            "source": row[1],
            "name": row[2],
            "symbol": row[3],
            "quantity": row[4],
            "average_price": row[5],
            "created_at": row[6],
        }
        for row in rows
    ]


def portfolio_value(current_prices: dict[str, float], db_path: str | Path | None = None) -> dict:
    positions = list_positions(db_path)
    holdings = []
    total_cost = 0.0
    total_value = 0.0

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
                "name": position.get("name") or symbol,
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