from pathlib import Path

from src.trading.core.alerts import create_price_alert, evaluate_price_alerts
from src.trading.core.backtesting import moving_average_crossover_backtest
from src.trading.core.portfolio import add_position, list_positions, portfolio_value
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