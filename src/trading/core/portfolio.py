from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
import sqlite3
from typing import Iterable

import requests

from .utils import get_api_key

try:
    import yfinance as yf
except ModuleNotFoundError:
    yf = None


DEFAULT_PORTFOLIO_DB_PATH = Path.home() / ".trading_portfolio.sqlite3"
OPENFIGI_MAP_URL = "https://api.openfigi.com/v3/mapping"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
_ISIN_RESOLUTION_CACHE: dict[str, tuple[str | None, str]] = {}
_DEFAULT_ISIN_RESOLVERS = ("finnhub", "openfigi", "wikidata")
_LOCAL_ISIN_NAME_FALLBACKS: dict[str, str] = {}
_LOCAL_SYMBOL_NAME_FALLBACKS: dict[str, str] = {
    "A1C4D4": "Wagner & Florack Unternehmerfonds",
    "973105": "Seilern Global Trust A",
    "DWS0UY": "FOCAM Capital Growth Fund SD",
    "A3EHRE": "JPM Global Equity Premium",
    "A3DSTH": "Amundi S&P World Information",
    "ETFL18": "Deka Deutsche Boerse EUROGOV",
    "A2DL7E": "Fidelity Global Quality Income",
    "A2JEX5": "Yellow Cake Rg",
    "A3DNGW": "Woodside Energy",
    "WCH888": "Wacker Chemie",
    "A1CX3T": "Tesla",
    "A42D4F": "SpaceX",
    "863403": "Santos",
    "861149": "RTL",
    "A3E5D5": "Fuchs",
}


def _get_isin_resolvers() -> tuple[str, ...]:
    raw_value = os.getenv("PORTFOLIO_ISIN_RESOLVERS", "").strip()
    if not raw_value:
        return _DEFAULT_ISIN_RESOLVERS

    resolvers = tuple(part.strip().lower() for part in raw_value.split(",") if part.strip())
    return resolvers or _DEFAULT_ISIN_RESOLVERS


def _normalize_source(source: str | None) -> str:
    return str(source or "manual").strip().lower() or "manual"


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db_path or DEFAULT_PORTFOLIO_DB_PATH))
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS portfolio_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL DEFAULT 'manual',
            name_source TEXT,
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
    try:
        connection.execute("ALTER TABLE portfolio_positions ADD COLUMN name_source TEXT")
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
    name_source: str | None = None,
) -> int:
    normalized_source = _normalize_source(source)
    with _connect(db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO portfolio_positions (source, name_source, name, symbol, quantity, average_price) VALUES (?, ?, ?, ?, ?, ?)",
            (normalized_source, name_source, name, symbol.upper(), quantity, average_price),
        )
        return int(cursor.lastrowid)


def update_position(
    position_id: int,
    symbol: str,
    quantity: float,
    average_price: float,
    source: str = "manual",
    name: str | None = None,
    name_source: str | None = None,
    db_path: str | Path | None = None,
) -> None:
    normalized_source = _normalize_source(source)
    with _connect(db_path) as connection:
        connection.execute(
            "UPDATE portfolio_positions SET source = ?, name_source = ?, name = ?, symbol = ?, quantity = ?, average_price = ? WHERE id = ?",
            (normalized_source, name_source, name, symbol.upper(), quantity, average_price, position_id),
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


def _resolve_isin_metadata(isin: str) -> tuple[str | None, str]:
    if not isin:
        return None, "none"

    cached = _ISIN_RESOLUTION_CACHE.get(isin)
    if cached is not None:
        return cached

    for resolver in _get_isin_resolvers():
        if resolver == "finnhub":
            finnhub_key = None
            try:
                finnhub_key = get_api_key("finnhub")
            except Exception:
                finnhub_key = None

            if not finnhub_key:
                continue

            try:
                response = requests.get(
                    "https://finnhub.io/api/v1/search",
                    params={"q": isin, "token": finnhub_key},
                    timeout=15,
                )
                response.raise_for_status()
                data = response.json()
            except Exception:
                continue

            for item in data.get("result", []) if isinstance(data, dict) else []:
                if not isinstance(item, dict):
                    continue
                description = item.get("description")
                if isinstance(description, str) and description.strip():
                    result = (description.strip(), "finnhub")
                    _ISIN_RESOLUTION_CACHE[isin] = result
                    return result

        elif resolver == "openfigi":
            payload = [{"idType": "ID_ISIN", "idValue": isin}]
            try:
                response = requests.post(OPENFIGI_MAP_URL, json=payload, timeout=15)
                response.raise_for_status()
                data = response.json()
            except Exception:
                continue

            if not isinstance(data, dict):
                continue

            for item in data.get("data", []):
                if not isinstance(item, dict) or item.get("error"):
                    continue
                for key in ("name", "securityName", "ticker"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        result = (value.strip(), "openfigi")
                        _ISIN_RESOLUTION_CACHE[isin] = result
                        return result

        elif resolver == "wikidata":
            query = f'''
            SELECT ?itemLabel WHERE {{
              ?item wdt:P212 "{isin}".
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "de,en". }}
            }}
            LIMIT 5
            '''

            try:
                response = requests.get(
                    WIKIDATA_SPARQL_URL,
                    params={"format": "json", "query": query},
                    headers={"Accept": "application/sparql-results+json", "User-Agent": "Mozilla/5.0"},
                    timeout=20,
                )
                response.raise_for_status()
                data = response.json()
            except Exception:
                continue

            for binding in data.get("results", {}).get("bindings", []) if isinstance(data, dict) else []:
                if not isinstance(binding, dict):
                    continue
                label = binding.get("itemLabel", {}).get("value") if isinstance(binding.get("itemLabel"), dict) else None
                if isinstance(label, str) and label.strip():
                    result = (label.strip(), "wikidata")
                    _ISIN_RESOLUTION_CACHE[isin] = result
                    return result

    result = (_LOCAL_ISIN_NAME_FALLBACKS.get(isin), "local" if isin in _LOCAL_ISIN_NAME_FALLBACKS else "none")
    _ISIN_RESOLUTION_CACHE[isin] = result
    return result


def _resolve_name_from_isin(isin: str) -> str | None:
    return _resolve_isin_metadata(isin)[0]


def _resolve_name_from_symbol(symbol: str) -> tuple[str | None, str]:
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        return None, "none"

    finnhub_key = None
    try:
        finnhub_key = get_api_key("finnhub")
    except Exception:
        finnhub_key = None

    if finnhub_key:
        try:
            response = requests.get(
                "https://finnhub.io/api/v1/search",
                params={"q": normalized_symbol, "token": finnhub_key},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            data = None

        for item in data.get("result", []) if isinstance(data, dict) else []:
            if not isinstance(item, dict):
                continue
            for key in ("description", "displaySymbol", "symbol"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    resolved = value.strip()
                    if not _looks_like_placeholder_name(resolved, normalized_symbol):
                        return resolved, "finnhub"

    if yf is not None:
        try:
            search = yf.Search(normalized_symbol, max_results=5)
            for result in getattr(search, "quotes", []) or []:
                if not isinstance(result, dict):
                    continue
                result_symbol = str(result.get("symbol") or "").strip().upper()
                if result_symbol and result_symbol != normalized_symbol and not result_symbol.startswith(normalized_symbol):
                    continue
                for key in ("longname", "shortname", "name", "displayName"):
                    value = result.get(key)
                    if isinstance(value, str) and value.strip():
                        resolved = value.strip()
                        if not _looks_like_placeholder_name(resolved, normalized_symbol):
                            return resolved, "yfinance"
        except Exception:
            pass

    return None, "none"


def _read_pdf_tables(file_path: str | Path) -> list[list[list[str]]]:
    try:
        import pdfplumber
    except ModuleNotFoundError:
        return []

    tables: list[list[list[str]]] = []
    with pdfplumber.open(str(file_path)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                cleaned_table = [["" if cell is None else str(cell).strip() for cell in row] for row in table if any(cell for cell in row)]
                if cleaned_table:
                    tables.append(cleaned_table)
    return tables


def _parse_quantity(value: str) -> float:
    cleaned = value.strip().replace(" ", "")
    if not cleaned:
        raise ValueError("empty numeric value")

    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif cleaned.count(".") > 1:
        cleaned = cleaned.replace(".", "")
    else:
        parts = cleaned.split(".")
        if len(parts) == 2 and len(parts[1]) == 3 and parts[0].isdigit() and parts[1].isdigit():
            cleaned = "".join(parts)

    return float(cleaned)


def _normalize_pdf_name(name: str | None) -> str | None:
    if not name:
        return None

    cleaned = re.sub(r"\s+", " ", name).strip()
    cleaned = re.sub(r"\b([A-Za-z]{3,})\s+([a-z])\b", r"\1\2", cleaned)
    cleaned = re.sub(r"\b([A-Za-z]{5,})\s+([a-z])\b", r"\1\2", cleaned)
    return cleaned or None


def _is_meaningful_pdf_name(name: str | None) -> bool:
    cleaned = _normalize_pdf_name(name)
    if not cleaned:
        return False
    if len(cleaned) < 4:
        return False
    if cleaned.lower() in {"div", "rg", "ors", "e", "a"}:
        return False
    if cleaned in {"O.N.", "(Vz)", "(vinkuliert)", "Information", "Equity Swap"}:
        return False
    return bool(re.search(r"[A-Za-zÄÖÜäöüß]", cleaned)) and " " in cleaned or len(cleaned) >= 8


def _parse_ing_pdf_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    row_pattern = re.compile(r"^(?P<name>.*?)\s*(?P<symbol>[A-Z0-9]{4,12})\s+(?P<isin>[A-Z]{2}[A-Z0-9]{10})\s+(?P<quantity>[\d.,]+)\s+(?P<price>[\d.,]+)")

    pending_rows: list[dict[str, str | None]] = []
    pending_names: list[str] = []
    collecting_names = False

    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            continue

        if line.startswith(("Tabelle", "Seite")) or line in {"Name AWK ISIN Anzahl", "Kaufpreis Stück Kaufpreis gesamt Gesamtpreis"}:
            continue

        if line.startswith(("Kaufpreis", "Gesamtpreis", "Fonds", "ETFs", "Aktien")):
            collecting_names = True
            continue

        row_match = row_pattern.search(line)
        if row_match:
            name = row_match.group("name").strip() or None
            if name and name.upper() == row_match.group("symbol").upper():
                name = None
            if name:
                name = _normalize_pdf_name(name)
            pending_rows.append(
                {
                    "name": name,
                    "symbol": row_match.group("symbol").upper(),
                    "quantity": row_match.group("quantity"),
                    "average_price": row_match.group("price"),
                    "isin": row_match.group("isin"),
                }
            )
            collecting_names = False
            continue

        if collecting_names and _looks_like_pdf_name(line) and not re.search(r"\d", line):
            pending_names.append(line)

    pending_names = _combine_pdf_name_fragments(pending_names)

    name_index = 0
    for row in pending_rows:
        if not row["name"] and name_index < len(pending_names):
            row["name"] = _normalize_pdf_name(pending_names[name_index])
            name_index += 1
        key = (row["symbol"], row["isin"])
        if key not in seen:
            seen.add(key)
            rows.append({
                "name": row["name"],
                "symbol": row["symbol"],
                "quantity": row["quantity"],
                "average_price": row["average_price"],
                "isin": row["isin"],
            })
    return rows


def _find_column(row: dict[str, str], candidates: Iterable[str]) -> str | None:
    normalized = {key.strip().lower().replace(" ", "_"): key for key in row}
    for candidate in candidates:
        key = normalized.get(candidate)
        if key:
            return key
    return None


def _looks_like_symbol(value: str) -> bool:
    cleaned = value.strip().upper()
    return bool(cleaned) and not cleaned.isdigit() and bool(re.fullmatch(r"[A-Z0-9._-]{1,15}", cleaned))


def _looks_like_pdf_name(value: str) -> bool:
    cleaned = value.strip()
    if not cleaned:
        return False
    if cleaned in {
        "Stück",
        "O.N.",
        "gesamt",
        "Kaufpreis",
        "Gesamtpreis",
        "Fonds",
        "ETFs",
        "Aktien",
        "Name",
        "AWK",
        "ISIN",
        "Anzahl",
        "Kaufpreis gesamt",
        "Kaufpreis Stück",
        "Gesamtpreis 26.08.2026",
        "Seite",
    }:
        return False
    if cleaned.startswith("Tabelle") or cleaned.startswith("Seite"):
        return False
    return bool(re.search(r"[A-Za-zÄÖÜäöüß]", cleaned))


def _parse_pdf_table_rows(tables: list[list[list[str]]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for table in tables:
        if not table:
            continue

        header = [cell.strip().lower() for cell in table[0]]
        if not any("isin" in cell for cell in header):
            continue

        symbol_index = next((index for index, cell in enumerate(header) if cell in {"awk", "symbol", "ticker"}), None)
        isin_index = next((index for index, cell in enumerate(header) if "isin" in cell), None)
        quantity_index = next((index for index, cell in enumerate(header) if any(token in cell for token in {"anzahl", "quantity", "shares", "stück", "stueck"})), None)
        price_index = next((index for index, cell in enumerate(header) if any(token in cell for token in {"kaufpreis", "preis", "average_price", "avg_price", "purchase_price"})), None)

        if symbol_index is None or isin_index is None or quantity_index is None or price_index is None:
            continue

        for row in table[1:]:
            if max(symbol_index, isin_index, quantity_index, price_index) >= len(row):
                continue

            symbol = row[symbol_index].strip().upper()
            isin = row[isin_index].strip().upper()
            quantity_text = row[quantity_index].strip()
            average_price_text = row[price_index].strip()
            name = row[0].strip() if symbol_index > 0 else None

            if not _looks_like_symbol(symbol) or not isin:
                continue

            key = (symbol, isin)
            if key in seen:
                continue
            seen.add(key)

            resolved_name, resolved_source = _resolve_isin_metadata(isin)
            if not resolved_name:
                resolved_name = _normalize_pdf_name(name)
                resolved_source = "pdf" if resolved_name else "none"

            rows.append(
                {
                    "name": resolved_name,
                    "name_source": resolved_source,
                    "symbol": symbol,
                    "quantity": quantity_text,
                    "average_price": average_price_text,
                    "isin": isin,
                }
            )

    return rows


def _combine_pdf_name_fragments(fragments: list[str]) -> list[str]:
    combined: list[str] = []
    pending: list[str] = []

    def flush() -> None:
        nonlocal pending
        if pending:
            name = _normalize_pdf_name(" ".join(pending))
            if name:
                combined.append(name)
        pending = []

    for fragment in fragments:
        if not _looks_like_pdf_name(fragment):
            flush()
            continue

        if fragment in {"O.N.", "Rg"}:
            if pending:
                pending.append(fragment)
            continue

        if fragment.startswith(("(",)) or fragment.endswith(".") and len(fragment) <= 4:
            if pending:
                pending.append(fragment)
            continue

        if pending and len(" ".join(pending)) > 20:
            flush()

        pending.append(fragment)

        if len(pending) >= 2 and len(fragment) > 4:
            flush()

    flush()
    return combined


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
    unresolved: list[str] = []

    if replace:
        delete_positions_by_source(source, db_path)

    for row in rows:
        symbol_column = _find_column(row, ("symbol", "ticker", "security", "wertpapier", "asset"))
        quantity_column = _find_column(row, ("quantity", "pieces", "units", "amount", "shares"))
        price_column = _find_column(row, ("average_price", "avg_price", "purchase_price", "price", "entry_price"))

        if not symbol_column or not quantity_column or not price_column:
            skipped += 1
            continue

        symbol = str(row[symbol_column]).strip().upper()
        quantity_text = str(row[quantity_column]).strip().replace(",", ".")
        price_text = str(row[price_column]).strip().replace(",", ".")

        if not _looks_like_symbol(symbol):
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
        "unresolved": unresolved,
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
    tables = _read_pdf_tables(file_path)
    rows = _parse_pdf_table_rows(tables) if tables else _parse_ing_pdf_rows(_read_pdf_text(file_path))
    imported = 0
    skipped = 0
    unresolved: list[str] = []

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

        resolved_name = None
        resolved_source = "none"

        resolved_name, resolved_source = _resolve_isin_metadata(row["isin"])

        if not resolved_name:
            resolved_name, resolved_source = _resolve_name_from_symbol(symbol)

        if not resolved_name:
            pdf_name = row.get("name")
            if _is_meaningful_pdf_name(pdf_name):
                resolved_name = _normalize_pdf_name(pdf_name)
                resolved_source = "pdf"

        if not resolved_name:
            fallback_name = _LOCAL_SYMBOL_NAME_FALLBACKS.get(symbol)
            if fallback_name:
                resolved_name = fallback_name
                resolved_source = "local"

        if not resolved_name:
            resolved_source = "none"
            unresolved.append(f"{symbol}/{row['isin']}")

        add_position(symbol, quantity, average_price, db_path=db_path, source=source, name=resolved_name, name_source=resolved_source)
        imported += 1

    return {
        "imported": imported,
        "skipped": skipped,
        "unresolved": unresolved,
        "rows": len(rows),
        "format": "pdf",
    }


def list_positions(db_path: str | Path | None = None) -> list[dict]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT id, source, name_source, name, symbol, quantity, average_price, created_at FROM portfolio_positions ORDER BY created_at DESC"
        ).fetchall()

    return [
        {
            "id": row[0],
            "source": row[1],
            "name_source": row[2],
            "name": row[3],
            "symbol": row[4],
            "quantity": row[5],
            "average_price": row[6],
            "created_at": row[7],
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