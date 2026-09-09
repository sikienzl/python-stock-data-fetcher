from pathlib import Path

from src.trading.core.alerts import create_price_alert, evaluate_price_alerts
from src.trading.core.backtesting import moving_average_crossover_backtest
from src.trading.core.portfolio import add_position, list_positions, portfolio_value, _resolve_isin_metadata
from src.trading.core.storage import load_quotes, save_quote
from src.trading.core.comparison import compare_providers


def test_sqlite_quote_roundtrip():
    db = Path("/tmp/trading_quotes_test.sqlite3")
    db.unlink(missing_ok=True)
    save_quote("AAPL", "finnhub", {"c": 123.45}, db)
    quotes = load_quotes("AAPL", "finnhub", db)
    assert quotes[0]["payload"]["c"] == 123.45
    db.unlink(missing_ok=True)


def test_alerts_and_backtest_smoke():
    db = Path("/tmp/trading_alerts_test.sqlite3")
    db.unlink(missing_ok=True)
    alert_id = create_price_alert("AAPL", ">", 100, db)
    assert alert_id > 0
    triggered = evaluate_price_alerts("AAPL", 101, db)
    assert triggered
    result = moving_average_crossover_backtest([100 + i for i in range(30)])
    assert result["total_trades"] >= 0
    db.unlink(missing_ok=True)


def test_portfolio_and_comparison_smoke():
    db = Path("/tmp/trading_portfolio_test.sqlite3")
    db.unlink(missing_ok=True)
    add_position("AAPL", 2, 100, db)
    positions = list_positions(db)
    assert positions[0]["symbol"] == "AAPL"
    value = portfolio_value({"AAPL": 110}, db)
    assert value["total_value"] == 220
    comparison = compare_providers("AAPL", ["finnhub"])
    assert comparison["symbol"] == "AAPL"
    db.unlink(missing_ok=True)


def test_portfolio_resolver_metadata_cache(monkeypatch):
    calls = {"count": 0}

    def fake_get_api_key(provider: str) -> str | None:
        return "token" if provider == "finnhub" else None

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            calls["count"] += 1
            return {"result": [{"description": "Aktienbrauerei Kaufbeuren AG"}]}

    monkeypatch.setattr("src.trading.core.portfolio.get_api_key", fake_get_api_key)
    monkeypatch.setattr("src.trading.core.portfolio.requests.get", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr("src.trading.core.portfolio.requests.post", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr("src.trading.core.portfolio._ISIN_RESOLUTION_CACHE", {})

    first = _resolve_isin_metadata("DE0005013007")
    second = _resolve_isin_metadata("DE0005013007")

    assert first == ("Aktienbrauerei Kaufbeuren AG", "finnhub")
    assert second == first
    assert calls["count"] == 1


def test_portfolio_persists_name_source(tmp_path: Path):
    db = tmp_path / "portfolio.db"
    position_id = add_position("TEST", 1, 2.5, db_path=db, name="Example AG", name_source="pdf")
    positions = list_positions(db)

    assert position_id > 0
    assert positions[0]["name"] == "Example AG"
    assert positions[0]["name_source"] == "pdf"