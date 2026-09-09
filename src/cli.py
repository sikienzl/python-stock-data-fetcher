import click
from datetime import datetime, timezone

from trading import (
    add_position,
    compare_providers,
    analyze_prices,
    create_price_alert,
    evaluate_price_alerts,
    fetch_finnhub_news,
    fetch_trading_news,
    fetch_data,
    FinnhubClient,
    list_positions,
    list_price_alerts,
    moving_average_crossover_backtest,
    portfolio_value,
)

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


@cli.command()
def portfolio_list():
    positions = list_positions()
    if not positions:
        click.echo("No positions stored.")
        return
    for position in positions:
        click.echo(
            f"{position['symbol']}: {position['quantity']} @ {position['average_price']}"
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
    result = compare_providers(symbol, [provider.strip() for provider in providers.split(",") if provider.strip()])
    click.echo(f"Comparison for {result['symbol']}")
    for provider, payload in result["results"].items():
        click.echo(f"{provider}: {payload}")

if __name__ == "__main__":
    cli()