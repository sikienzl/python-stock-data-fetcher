from pathlib import Path

from src.trading.core.alerts import create_price_alert, evaluate_price_alerts
from src.trading.core.candlesticks import detect_candlestick_patterns
from src.trading.core.export import export_to_csv, export_to_json
from src.trading.core.performance import portfolio_metrics
from src.trading.core.risk import calculate_position_size, calculate_stop_loss
from src.trading.core.strategy_backtests import backtest_rsi_strategy, compare_strategies


def test_portfolio_metrics_and_exports():
    metrics = portfolio_metrics({"AAPL": 110}, db_path=Path("/tmp/nonexistent.sqlite3"))
    assert metrics["total_value"] == 0

    records = [{"symbol": "AAPL", "pnl": 12.5}]
    csv_path = export_to_csv(records, "/tmp/trading_export.csv")
    json_path = export_to_json(records, "/tmp/trading_export.json")
    assert csv_path.exists()
    assert json_path.exists()
    csv_path.unlink(missing_ok=True)
    json_path.unlink(missing_ok=True)


def test_risk_alert_and_strategy_helpers():
    assert calculate_stop_loss(100) == 95.0
    assert calculate_position_size(10000, 0.02, 100, 95) == 40.0

    alert_db = Path("/tmp/trading_advanced_alerts.sqlite3")
    alert_db.unlink(missing_ok=True)
    create_price_alert("AAPL", ">", 100, alert_db)
    assert evaluate_price_alerts("AAPL", 101, alert_db)

    assert backtest_rsi_strategy([100 + i for i in range(30)])
    assert compare_strategies([100 + i for i in range(30)])
    assert detect_candlestick_patterns([
        {"o": 100, "c": 101, "h": 102, "l": 99, "t": 1, "symbol": "AAPL"}
    ])
    alert_db.unlink(missing_ok=True)