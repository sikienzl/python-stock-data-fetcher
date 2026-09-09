# python-stock-data-fetcher
A Python client to fetch stock market data from Finnhub.io and Alpha Vantage APIs.

## Installation
Install the package via install script:
``` 
$ sh install_data_fetcher.sh
``` 
For development or local testing, clone the repository and install in editable mode:
``` 
$ git clone https://github.com/sikienzl/python-stock-data-fetcher.git
$ cd python-stock-data-fetcher
$ git checkout develop
$ pip3 install -r requirements.txt
```

## Contributing
Contributions are welcome! Feel free to:
* Report issues: [GitHub Issues](https://github.com/sikienzl/python-stock-data-fetcher/issues)
* Submit pull requests for improvements.

## Project Structure
The codebase uses a single package root under `src/trading/` for application logic:

* `src/trading/core/` - data fetching, storage, alerts, backtesting, portfolio, and provider comparison
* `src/trading/providers/` - Finnhub and Alpha Vantage integrations
* `src/trading/analysis/` - technical indicators and analysis helpers
* `src/cli.py` - command line entry point

## Configuration
1. Add your API keys to a `.env` file:
```
FINNHUB_API_KEY=your_finnhub_key
ALPHAVANTAGE_API_KEY=your_alpha_vantage_key
```
2. The `.env` file will be automatically loaded when using the client.

## **Data Analysis: Technical Indicators**
The package now includes technical analysis helpers for price series:

* `SMA` - simple moving average
* `EMA` - exponential moving average
* `RSI` - relative strength index
* `MACD` - moving average convergence divergence

Example CLI usage:
```bash
python3 src/cli.py analyze --prices "100,101,102,103,104,105,106,107,108,109,110,111,112,113,114"
```

## **Store Historical Data (SQLite)**
Stock quotes are stored locally in SQLite for backtesting and offline analysis.

* Default database: `~/.trading_stock_data.sqlite3`
* Each API fetch is persisted automatically unless disabled with `save_to_db=False`
* Historical quotes can be loaded again with `load_quotes()`

Example usage:
```python
from trading import fetch_data, load_quotes

quote = fetch_data("AAPL", provider="finnhub")
history = load_quotes("AAPL", provider="finnhub")
```

## **Automation & Alerts**
The CLI now supports price alerts, basic backtesting, portfolio tracking, and provider comparison.

Examples:
```bash
python3 src/cli.py alert
python3 src/cli.py check-alerts
python3 src/cli.py backtest
python3 src/cli.py portfolio-add
python3 src/cli.py portfolio-list
python3 src/cli.py portfolio-value
python3 src/cli.py compare
```

## **Advanced Workflow Additions**
The CLI now includes extra commands for the next growth steps:

* `portfolio-metrics` for ROI, Sharpe ratio, and max drawdown.
* `alert-send` for Telegram or email notification hooks.
* `export` for CSV or JSON output.
* `backtest-compare` for comparing multiple strategies.
* `risk` for stop-loss and position sizing.
* `candles` for simple candlestick pattern detection.
* `dashboard` for the local web server.

Example usage:
```bash
python3 src/cli.py portfolio-metrics
python3 src/cli.py alert-send
python3 src/cli.py export
python3 src/cli.py backtest-compare
python3 src/cli.py risk
python3 src/cli.py candles
python3 src/cli.py dashboard
```

## **Local Web Dashboard**
The project now includes a lightweight web dashboard that runs without extra dependencies.

* Default URL: `http://0.0.0.0:8000`
* Works well on a Raspberry Pi or in Docker
* Shows portfolio metrics, alerts, recent stored quotes, and quick API actions

Run it with:
```bash
python3 src/cli.py dashboard
```

Available JSON endpoints:
* `GET /api/quotes`
* `GET /api/alerts`
* `GET /api/portfolio`
* `GET /api/compare?symbol=AAPL`

## **Advanced Features**
* Price alerts are stored in SQLite and can be evaluated against live prices.
* Backtesting currently includes a moving-average crossover strategy.
* Portfolio positions are stored locally and can be valued against current prices.
* Provider comparison fetches the same symbol from multiple APIs and returns the results side by side.

## License
[Apache License Version 2.0](https://github.com/sikienzl/python-stock-data-fetcher/blob/main/LICENSE)

Maintainer contact: sikienzl.github@t-online.de