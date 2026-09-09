import click
from datetime import datetime, timezone

from trading import (
    add_position,
    backtest_rsi_strategy,
    backtest_sma_crossover,
    compare_providers,
    compare_strategies,
    analyze_prices,
    calculate_position_size,
    calculate_stop_loss,
    create_price_alert,
    delete_all_positions,
    delete_position,
    delete_price_alert,
    detect_candlestick_patterns,
    evaluate_price_alerts,
    export_to_csv,
    export_to_json,
    fetch_currents_news,
    fetch_finnhub_news,
    fetch_trading_news,
    fetch_data,
    FinnhubClient,
    import_positions_from_csv,
    import_positions_from_pdf,
    portfolio_metrics,
    list_positions,
    list_price_alerts,
    moving_average_crossover_backtest,
    portfolio_value,
    send_email_message,
    send_telegram_message,
    update_position,
    update_price_alert,
)
from trading.dashboard import run_dashboard_server
from trading.core.rate_limit import get_provider_min_interval

@click.group()
def cli():
    pass

@cli.command()
@click.option("--symbol", prompt="Stock symbol", help="The stock symbol to stream quotes for.")
@click.option("--provider", prompt="Data provider", help="The data provider to use.")
def fetch(symbol, provider):
    try:
        data = fetch_data(symbol, provider=provider)
        click.echo(f"Fetched data for {symbol} from {provider}: {data}")
    except Exception as e:
        click.echo(f"Error fetching data: {e}")

@cli.command()
def news():
    click.echo("Fetching Finnhub news...")
    fetch_finnhub_news()

    click.echo("Fetching Alpha Vantage news...")
    fetch_trading_news()

    click.echo("Fetching Currents API news...")
    fetch_currents_news()

@cli.command()
@click.option("--symbol", prompt="Stock symbol", help="The stock symbol to stream.")
@click.option("--limit", type=click.IntRange(min=1), default=None, help="Stop after N streamed quote messages.")
def stream(symbol, limit):
    click.echo(f"Streaming real-time Finnhub quotes for {symbol}... Press Ctrl+C to stop.")

    client = FinnhubClient()

    def print_quote(message: dict) -> None:
        price = message.get("p")
        timestamp = message.get("t")
        if timestamp:
            human_time = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        else:
            human_time = "unknown time"
        click.echo(f"{symbol}: {price} at {human_time}")

    try:
        client.stream_quotes(symbol, print_quote, max_messages=limit)
    except Exception as e:
        click.echo(f"Error streaming quotes: {e}")


@cli.command()
@click.option("--prices", prompt="Comma-separated prices", help="Comma-separated list of prices for technical analysis.")
@click.option("--period", type=click.IntRange(min=2), default=14, show_default=True)
def analyze(prices, period):
    values = [float(value.strip()) for value in prices.split(",") if value.strip()]
    result = analyze_prices(values, period=period)

    click.echo("Technical Indicators:")
    click.echo(f"SMA ({period}): {result['sma']:.4f}")
    click.echo(f"EMA ({period}): {result['ema']:.4f}")
    click.echo(f"RSI ({period}): {result['rsi']:.4f}")
    click.echo(
        "MACD: "
        f"{result['macd']['macd']:.4f} / "
        f"Signal: {result['macd']['signal']:.4f} / "
        f"Histogram: {result['macd']['histogram']:.4f}"
    )


@cli.command()
@click.option("--symbol", prompt="Stock symbol")
@click.option("--operator", type=click.Choice([">", "<", ">=", "<="]), prompt="Alert operator")
@click.option("--target-price", type=float, prompt="Target price")
def alert(symbol, operator, target_price):
    alert_id = create_price_alert(symbol, operator, target_price)
    click.echo(f"Created alert #{alert_id} for {symbol.upper()} {operator} {target_price}")


@cli.command("alert-update")
@click.option("--alert-id", type=int, prompt="Alert ID")
@click.option("--symbol", prompt="Stock symbol")
@click.option("--operator", type=click.Choice([">", "<", ">=", "<="]), prompt="Alert operator")
@click.option("--target-price", type=float, prompt="Target price")
@click.option("--active/--inactive", default=True, show_default=True)
def alert_update(alert_id, symbol, operator, target_price, active):
    update_price_alert(alert_id, symbol, operator, target_price, active=active)
    click.echo(f"Updated alert #{alert_id}.")


@cli.command("alert-delete")
@click.option("--alert-id", type=int, prompt="Alert ID")
def alert_delete(alert_id):
    delete_price_alert(alert_id)
    click.echo(f"Deleted alert #{alert_id}.")


@cli.command()
@click.option("--symbol", prompt="Stock symbol")
@click.option("--current-price", type=float, prompt="Current price")
def check_alerts(symbol, current_price):
    triggered = evaluate_price_alerts(symbol, current_price)
    if not triggered:
        click.echo("No alerts triggered.")
        return
    for item in triggered:
        click.echo(
            f"Alert triggered for {item['symbol']}: {item['operator']} {item['target_price']} at {item['current_price']}"
        )


@cli.command()
@click.option("--prices", prompt="Comma-separated prices")
@click.option("--fast-period", type=click.IntRange(min=1), default=5, show_default=True)
@click.option("--slow-period", type=click.IntRange(min=2), default=20, show_default=True)
def backtest(prices, fast_period, slow_period):
    values = [float(value.strip()) for value in prices.split(",") if value.strip()]
    result = moving_average_crossover_backtest(values, fast_period=fast_period, slow_period=slow_period)
    click.echo(f"Strategy: {result['strategy']}")
    click.echo(f"Total trades: {result['total_trades']}")
    click.echo(f"Realized PnL: {result['realized_pnl']:.4f}")


@cli.command()
@click.option("--symbol", prompt="Stock symbol")
@click.option("--quantity", type=float, prompt="Quantity")
@click.option("--average-price", type=float, prompt="Average price")
def portfolio_add(symbol, quantity, average_price):
    position_id = add_position(symbol, quantity, average_price)
    click.echo(f"Added position #{position_id} for {symbol.upper()}")


@cli.command("portfolio-import-csv")
@click.option("--file", "file_path", type=click.Path(exists=True, dir_okay=False, path_type=str), prompt="CSV file path")
@click.option("--source", default="manual", show_default=True, help="Source/provider label such as ING or XTB.")
@click.option("--replace/--append", default=False, show_default=True, help="Replace existing positions before importing.")
def portfolio_import_csv(file_path, source, replace):
    result = import_positions_from_csv(file_path, replace=replace, source=source)
    click.echo(
        "Imported {imported} rows from {file} ({encoding}), skipped {skipped} of {rows}.".format(
            imported=result["imported"],
            file=file_path,
            encoding=result["encoding"],
            skipped=result["skipped"],
            rows=result["rows"],
        )
    )


@cli.command("portfolio-import-pdf")
@click.option("--file", "file_path", type=click.Path(exists=True, dir_okay=False, path_type=str), prompt="PDF file path")
@click.option("--source", default="ING", show_default=True, help="Source/provider label such as ING.")
@click.option("--replace/--append", default=False, show_default=True, help="Replace existing positions before importing.")
def portfolio_import_pdf(file_path, source, replace):
    result = import_positions_from_pdf(file_path, replace=replace, source=source)
    click.echo(
        "Imported {imported} rows from {file} ({format}), skipped {skipped} of {rows}.".format(
            imported=result["imported"],
            file=file_path,
            format=result["format"],
            skipped=result["skipped"],
            rows=result["rows"],
        )
    )


@cli.command()
def portfolio_list():
    positions = list_positions()
    if not positions:
        click.echo("No positions stored.")
        return
    for position in positions:
        click.echo(
            f"[{position['source']}] {position['symbol']}: {position['quantity']} @ {position['average_price']}"
        )


@cli.command("portfolio-value")
@click.option("--prices", prompt="Comma-separated symbol=price values")
def portfolio_value_cmd(prices):
    current_prices = {}
    for item in prices.split(","):
        if not item.strip():
            continue
        symbol, value = item.split("=", 1)
        current_prices[symbol.strip().upper()] = float(value.strip())
    result = portfolio_value(current_prices)
    click.echo(f"Total value: {result['total_value']:.4f}")
    click.echo(f"Total PnL: {result['total_pnl']:.4f}")


@cli.command()
@click.option("--symbol", prompt="Stock symbol")
@click.option("--providers", default="finnhub,alpha_vantage", show_default=True)
def compare(symbol, providers):
    providers_list = [provider.strip() for provider in providers.split(",") if provider.strip()]
    intervals = ", ".join(f"{provider}={get_provider_min_interval(provider)}s" for provider in providers_list)
    click.echo(f"Provider minimum intervals: {intervals}")
    result = compare_providers(symbol, providers_list)
    click.echo(f"Comparison for {result['symbol']}")
    for provider, payload in result["results"].items():
        click.echo(f"{provider}: {payload}")


@cli.command("portfolio-metrics")
@click.option("--prices", prompt="Comma-separated symbol=price values")
def portfolio_metrics_cmd(prices):
    current_prices = {}
    for item in prices.split(","):
        if not item.strip():
            continue
        symbol, value = item.split("=", 1)
        current_prices[symbol.strip().upper()] = float(value.strip())
    result = portfolio_metrics(current_prices)
    click.echo(f"ROI: {result['roi']:.4f}")
    click.echo(f"Sharpe Ratio: {result['sharpe_ratio']:.4f}")
    click.echo(f"Max Drawdown: {result['max_drawdown']:.4f}")


@cli.command("risk")
@click.option("--account-size", type=float, prompt="Account size")
@click.option("--risk-per-trade", type=float, prompt="Risk per trade (e.g. 0.02)")
@click.option("--entry-price", type=float, prompt="Entry price")
@click.option("--stop-loss-price", type=float, prompt="Stop-loss price")
def risk(account_size, risk_per_trade, entry_price, stop_loss_price):
    size = calculate_position_size(account_size, risk_per_trade, entry_price, stop_loss_price)
    stop_loss = calculate_stop_loss(entry_price)
    click.echo(f"Position size: {size:.4f}")
    click.echo(f"Suggested stop-loss: {stop_loss:.4f}")


@cli.command("export")
@click.option("--format", "export_format", type=click.Choice(["csv", "json"]), prompt="Export format")
@click.option("--output", prompt="Output file")
@click.option("--prices", prompt="Comma-separated symbol=price values")
def export_cmd(export_format, output, prices):
    current_prices = {}
    for item in prices.split(","):
        if not item.strip():
            continue
        symbol, value = item.split("=", 1)
        current_prices[symbol.strip().upper()] = float(value.strip())
    result = portfolio_metrics(current_prices)
    records = result["holdings"]
    if export_format == "csv":
        export_to_csv(records, output)
    else:
        export_to_json(records, output)
    click.echo(f"Exported {len(records)} records to {output}")


@cli.command("candles")
@click.option("--ohlc", prompt="Comma-separated candle JSON entries")
def candles(ohlc):
    import json

    candles_data = [json.loads(item) for item in ohlc.split("|") if item.strip()]
    patterns = detect_candlestick_patterns(candles_data)
    if not patterns:
        click.echo("No candlestick patterns detected.")
        return
    for pattern in patterns:
        click.echo(f"{pattern['pattern']} detected for {pattern.get('symbol', 'unknown')} at {pattern.get('date')}")


@cli.command("backtest-compare")
@click.option("--prices", prompt="Comma-separated prices")
def backtest_compare(prices):
    values = [float(value.strip()) for value in prices.split(",") if value.strip()]
    result = compare_strategies(values)
    click.echo(result)


@cli.command("alert-send")
@click.option("--message", prompt="Alert message")
@click.option("--channel", type=click.Choice(["telegram", "email"]), prompt="Channel")
def alert_send(message, channel):
    if channel == "telegram":
        success = send_telegram_message(message)
    else:
        success = send_email_message(message)
    click.echo("Alert sent." if success else "Alert could not be sent. Check configuration.")


@cli.command("dashboard")
@click.option("--host", default="0.0.0.0", show_default=True)
@click.option("--port", default=8000, type=click.IntRange(min=1, max=65535), show_default=True)
def dashboard(host, port):
    run_dashboard_server(host=host, port=port)

if __name__ == "__main__":
    cli()