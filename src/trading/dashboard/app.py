from __future__ import annotations

import json
import contextlib
import queue
import threading
import time
import io
from email.parser import BytesParser
from email.policy import default as email_default_policy
from dataclasses import dataclass
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

try:
    import yfinance as yf
except ModuleNotFoundError:
    yf = None


from trading import (
    add_position,
    create_price_alert,
    delete_position,
    delete_price_alert,
    detect_candlestick_patterns,
    evaluate_price_alerts,
    fetch_data,
    list_price_alerts,
    list_positions,
    load_quotes,
    moving_average_crossover_backtest,
    import_positions_from_csv,
    import_positions_from_pdf,
    get_api_key,
    portfolio_metrics,
    portfolio_value,
    update_position,
    update_price_alert,
)
from trading.core.rate_limit import get_provider_min_interval


@dataclass
class DashboardConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    title: str = "Trading Dashboard"
    refresh_interval: int = 15


class LiveUpdateHub:
    def __init__(self) -> None:
        self._subscribers: list[queue.Queue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        event_queue: queue.Queue = queue.Queue()
        with self._lock:
            self._subscribers.append(event_queue)
        return event_queue

    def unsubscribe(self, event_queue: queue.Queue) -> None:
        with self._lock:
            if event_queue in self._subscribers:
                self._subscribers.remove(event_queue)

    def publish(self, payload: dict) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for event_queue in subscribers:
            try:
                event_queue.put_nowait(payload)
            except queue.Full:
                continue


class DashboardState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot: dict = {
            "updated_at": None,
            "alerts": [],
            "quotes": [],
            "live_quotes": {},
            "metrics": {
                "holdings": [],
                "total_cost": 0.0,
                "total_value": 0.0,
                "total_pnl": 0.0,
                "roi": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
            },
            "tracked_symbols": [],
            "events": [],
        }

    def update(self, snapshot: dict) -> None:
        with self._lock:
            self._snapshot = snapshot

    def get(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self._snapshot, default=str))


STATE = DashboardState()
EVENT_HUB = LiveUpdateHub()

_NAME_CACHE: dict[str, str] = {}


def _tracked_symbols() -> list[str]:
    symbols: set[str] = set()
    for item in list_positions():
        symbols.add(item["symbol"])
    for item in list_price_alerts():
        symbols.add(item["symbol"])
    for item in load_quotes():
        symbols.add(item["symbol"])
    return sorted(symbols)


def _resolve_symbol_name(symbol: str) -> str | None:
    normalized_symbol = symbol.upper()
    if normalized_symbol in _NAME_CACHE:
        return _NAME_CACHE[normalized_symbol]

    if normalized_symbol.isdigit():
        return normalized_symbol

    def store(value: str | None) -> str | None:
        resolved = value.strip() if isinstance(value, str) else None
        if resolved:
            _NAME_CACHE[normalized_symbol] = resolved
        return resolved

    try:
        if yf is not None:
            with contextlib.redirect_stderr(io.StringIO()):
                search = yf.Search(normalized_symbol, max_results=5)
                for result in getattr(search, "quotes", []) or []:
                    result_symbol = str(result.get("symbol") or "").upper()
                    if result_symbol != normalized_symbol:
                        continue
                    resolved = store(
                        result.get("longname")
                        or result.get("shortname")
                        or result.get("name")
                        or result.get("displayName")
                    )
                    if resolved:
                        return resolved
    except Exception:
        pass

    return store(normalized_symbol)


def _looks_like_placeholder_name(name: str | None, symbol: str) -> bool:
    if not name:
        return True

    cleaned_name = name.strip()
    normalized_symbol = symbol.strip().upper()
    if not cleaned_name:
        return True
    if cleaned_name.upper() == normalized_symbol:
        return True
    if cleaned_name.isdigit():
        return True
    if cleaned_name.lower() in {"name unavailable", "unknown", "n/a", "na"}:
        return True
    return False


def _refresh_snapshot() -> dict:
    positions = list_positions()
    alerts = list_price_alerts()
    quote_history = load_quotes()
    tracked_symbols = _tracked_symbols()
    live_quotes: dict[str, dict] = {}
    events: list[dict] = []

    for symbol in tracked_symbols[:8]:
        try:
            live_quotes[symbol] = fetch_data(symbol, provider="finnhub", save_to_db=True)
            events.append({"type": "quote", "symbol": symbol, "payload": live_quotes[symbol]})
        except Exception as error:
            live_quotes[symbol] = {"error": str(error)}

    current_prices: dict[str, float] = {}
    for symbol, payload in live_quotes.items():
        if isinstance(payload, dict) and payload.get("c") is not None:
            current_prices[symbol] = float(payload["c"])
        elif isinstance(payload, dict) and payload.get("price") is not None:
            current_prices[symbol] = float(payload["price"])

    for position in positions:
        current_prices.setdefault(position["symbol"], float(position["average_price"]))

    names_by_symbol: dict[str, str] = {}
    for position in positions:
        stored_name = (position.get("name") or "").strip()
        symbol = position["symbol"]
        if stored_name and symbol not in names_by_symbol:
            names_by_symbol[symbol] = stored_name

    metrics = portfolio_metrics(current_prices)
    for holding in metrics.get("holdings", []):
        symbol = holding["symbol"]
        api_name = _resolve_symbol_name(symbol)
        stored_name = names_by_symbol.get(symbol) or holding.get("name")
        if api_name and api_name != symbol:
            holding["name"] = api_name
        else:
            holding["name"] = stored_name or api_name
    open_alerts = sum(1 for item in alerts if item["active"])
    snapshot = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "positions": positions,
        "alerts": alerts,
        "quotes": quote_history[:20],
        "live_quotes": live_quotes,
        "metrics": metrics,
        "tracked_symbols": tracked_symbols,
        "open_alerts": open_alerts,
        "events": events,
    }
    return snapshot


def _dashboard_worker(refresh_interval: int) -> None:
    while True:
        try:
            snapshot = _refresh_snapshot()
            STATE.update(snapshot)
            EVENT_HUB.publish(snapshot)
        except Exception as error:
            STATE.update({
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "positions": [],
                "alerts": [],
                "quotes": [],
                "live_quotes": {},
                "metrics": {
                    "holdings": [],
                    "total_cost": 0.0,
                    "total_value": 0.0,
                    "total_pnl": 0.0,
                    "roi": 0.0,
                    "sharpe_ratio": 0.0,
                    "max_drawdown": 0.0,
                },
                "tracked_symbols": [],
                "open_alerts": 0,
                "events": [{"type": "error", "message": str(error)}],
            })
        time.sleep(refresh_interval)


def _wrap_page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{escape(title)}</title>
  <style>
    :root {{ color-scheme: dark; --bg: #0b1020; --panel: #111a33; --muted: #8ea0c8; --text: #eef3ff; --accent: #63d2ff; --accent2: #9bffcb; --danger: #ff8ea1; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: radial-gradient(circle at top, #172043, var(--bg)); color: var(--text); }}
    header {{ padding: 24px; border-bottom: 1px solid rgba(255,255,255,.08); background: rgba(9,14,30,.55); position: sticky; top: 0; backdrop-filter: blur(16px); }}
    h1, h2, h3 {{ margin: 0 0 12px; }}
    main {{ padding: 24px; display: grid; gap: 18px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }}
    section {{ background: rgba(17,26,51,.88); border: 1px solid rgba(255,255,255,.08); border-radius: 18px; padding: 18px; box-shadow: 0 18px 40px rgba(0,0,0,.24); }}
    .full {{ grid-column: 1 / -1; }}
    .muted {{ color: var(--muted); }}
    .stat-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }}
    .stat {{ padding: 12px; border-radius: 14px; background: rgba(255,255,255,.04); }}
    .label {{ font-size: .8rem; color: var(--muted); }}
    .value {{ font-size: 1.4rem; font-weight: 700; margin-top: 6px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px 8px; border-bottom: 1px solid rgba(255,255,255,.08); text-align: left; }}
    th {{ color: var(--muted); font-weight: 600; }}
    input, select, button {{ width: 100%; padding: 10px 12px; border-radius: 12px; border: 1px solid rgba(255,255,255,.12); background: rgba(255,255,255,.04); color: var(--text); }}
    form {{ display: grid; gap: 10px; }}
    button {{ background: linear-gradient(135deg, var(--accent), var(--accent2)); color: #07111f; font-weight: 700; cursor: pointer; border: none; }}
    pre {{ overflow: auto; background: rgba(255,255,255,.04); padding: 12px; border-radius: 12px; }}
    .pill {{ display: inline-block; padding: 4px 10px; border-radius: 999px; background: rgba(99,210,255,.16); color: var(--accent); font-size: .8rem; }}
    .status {{ display: inline-flex; align-items: center; gap: 8px; }}
    .dot {{ width: 10px; height: 10px; border-radius: 999px; background: #4ee59a; box-shadow: 0 0 0 6px rgba(78,229,154,.12); }}
    a {{ color: var(--accent); }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(title)}</h1>
    <div class=\"muted status\"><span class=\"dot\"></span><span>Local dashboard for portfolio tracking, alerts, backtesting, analysis, and provider comparison.</span></div>
  </header>
  <main>
    {body}
  </main>
  <script>
    async function refreshSnapshot() {{
      try {{
        const response = await fetch('/api/snapshot');
        const snapshot = await response.json();
        const status = document.querySelector('[data-dashboard-status]');
        if (status) {{ status.textContent = 'Updated at ' + snapshot.updated_at; }}
      }} catch (error) {{
        console.error(error);
      }}
    }}

    function connectStream() {{
      const source = new EventSource('/events');
      source.onmessage = (event) => {{
        try {{
          const snapshot = JSON.parse(event.data);
          const status = document.querySelector('[data-dashboard-status]');
          if (status) {{ status.textContent = 'Live update ' + snapshot.updated_at; }}
          window.location.reload();
        }} catch (error) {{
          console.error(error);
        }}
      }};
      source.onerror = () => {{
        setTimeout(connectStream, 5000);
      }};
    }}

    refreshSnapshot();
    setInterval(refreshSnapshot, 5000);
    connectStream();
  </script>
</body>
</html>"""


def _stats_card(label: str, value: str) -> str:
    return f'<div class="stat"><div class="label">{escape(label)}</div><div class="value">{escape(value)}</div></div>'


def _render_grouped_portfolio(holdings: list[dict]) -> str:
    grouped: dict[str, list[dict]] = {}
    for item in holdings:
        grouped.setdefault(str(item.get("source", "manual")), []).append(item)

    if not grouped:
        return '<p class="muted">No positions stored.</p>'

    sections: list[str] = []
    row_number = 1
    for source in sorted(grouped):
        rows = grouped[source]
        table_rows = []
        for item in rows:
            display_name = item.get("name")
            table_rows.append(
                f"<tr><td>{row_number}</td><td>{escape(str(display_name)) if display_name else '<span class=\"muted\">Name unavailable</span>'}</td><td>{escape(str(item['symbol']))}</td><td>{item['quantity']}</td><td>{item['average_price']}</td><td>{item['current_price']}</td><td>{item['pnl']:.4f}</td><td>{_render_position_action(item)}</td></tr>"
            )
            row_number += 1
        sections.append(
            f'<h3>{escape(source)}</h3><table><thead><tr><th>#</th><th>Name</th><th>Symbol</th><th>Quantity</th><th>Avg Price</th><th>Current Price</th><th>PnL</th><th>Action</th></tr></thead><tbody>{"".join(table_rows)}</tbody></table>'
        )
    return ''.join(sections)


def _render_position_action(item: dict) -> str:
    position_id = item.get("id")
    if position_id is None:
        return '<span class="muted">Unavailable</span>'
    return (
        '<form method="post" action="/positions/delete" style="margin:0">'
        f'<input type="hidden" name="position_id" value="{position_id}" />'
        '<button type="submit">Delete</button>'
        '</form>'
    )


def _alert_operator_options() -> str:
    return (
        '<option value=">">&gt;</option>'
        '<option value="<">&lt;</option>'
        '<option value=">=">&gt;=</option>'
        '<option value="<=">&lt;=</option>'
    )


def _render_dashboard(import_message: str | None = None) -> str:
    snapshot = STATE.get()
    positions = snapshot.get("positions", [])
    alerts = snapshot.get("alerts", [])
    latest_quotes = snapshot.get("quotes", [])[:8]
    live_quotes = snapshot.get("live_quotes", {})
    metrics = snapshot.get("metrics", {})
    alerts_open = snapshot.get("open_alerts", 0)
    patterns = detect_candlestick_patterns([])

    body = f"""
        {f'<section><p class="muted">{escape(import_message)}</p></section>' if import_message else ''}

    <section>
      <h2>Overview</h2>
      <p class=\"muted\" data-dashboard-status>Waiting for first refresh...</p>
      <div class=\"stat-grid\">
        {_stats_card('Positions', str(len(positions)))}
        {_stats_card('Open Alerts', str(alerts_open))}
        {_stats_card('ROI', f"{metrics.get('roi', 0.0):.4f}")}
        {_stats_card('Sharpe Ratio', f"{metrics.get('sharpe_ratio', 0.0):.4f}")}
        {_stats_card('Max Drawdown', f"{metrics.get('max_drawdown', 0.0):.4f}")}
      </div>
    </section>

    <section>
                <select name="operator" required>
                    {_alert_operator_options()}
                </select>
      </form>
    </section>

    <section>
      <h2>Create Alert</h2>
      <form method=\"post\" action=\"/alerts/add\">
        <input name=\"symbol\" placeholder=\"Symbol\" required />
                <input name="source" placeholder="Source (ING, XTB, manual)" value="manual" />
            {_render_grouped_portfolio(metrics.get('holdings', []))}
          <option value=\">\">&gt;</option>
          <option value=\"<\">&lt;</option>
          <option value=\">=\">&gt;=</option>
          <option value=\"<=\">&lt;=</option>
        </select>
        <input name=\"target_price\" type=\"number\" step=\"0.0001\" placeholder=\"Target price\" required />
        <button type=\"submit\">Add Alert</button>
      </form>
    </section>

    <section class=\"full\">
      <h2>Portfolio</h2>
            {_render_grouped_portfolio(metrics.get('holdings', []))}
    </section>

    <section class=\"full\">
      <h2>Alerts</h2>
      <table>
        <thead><tr><th>Symbol</th><th>Rule</th><th>Target</th><th>Status</th></tr></thead>
        <tbody>
          {''.join(f"<tr><td>{escape(str(item['symbol']))}</td><td>{escape(str(item['operator']))}</td><td>{item['target_price']}</td><td>{'active' if item['active'] else 'triggered'}</td></tr>" for item in alerts) or '<tr><td colspan="4" class="muted">No alerts stored.</td></tr>'}
        </tbody>
      </table>
        </section>

        <section>
            <h2>Import CSV</h2>
            <form method="post" action="/portfolio/import-file" enctype="multipart/form-data">
                <select name="source" required>
                    <option value="ING">ING</option>
                    <option value="XTB">XTB</option>
                    <option value="IBKR">IBKR</option>
                    <option value="Kraken">Kraken</option>
                    <option value="other">Other</option>
                </select>
                <input name="portfolio_file" type="file" accept=".pdf,.csv,application/pdf,text/csv" required />
                <label class="muted"><input name="replace" type="checkbox" value="1" /> Replace existing positions for this source</label>
                <button type="submit">Import file</button>
            </form>
        </section>

    <section class=\"full\">
      <h2>Live Quotes</h2>
      <div class=\"stat-grid\">
        {''.join(_stats_card(symbol, f"{payload.get('c', payload.get('price', 'n/a'))}") for symbol, payload in live_quotes.items()) or _stats_card('Live Quotes', 'No live data yet')}
      </div>
    </section>

    <section class=\"full\">
      <h2>Recent Data</h2>
      <table>
        <thead><tr><th>Symbol</th><th>Provider</th><th>Fetched At</th><th>Payload</th></tr></thead>
        <tbody>
          {''.join(f"<tr><td>{escape(str(item['symbol']))}</td><td>{escape(str(item['provider']))}</td><td>{escape(str(item['fetched_at']))}</td><td><pre>{escape(json.dumps(item['payload'], indent=2))}</pre></td></tr>" for item in latest_quotes) or '<tr><td colspan="4" class="muted">No historical data stored yet.</td></tr>'}
        </tbody>
      </table>
    </section>

    <section class=\"full\">
      <h2>Quick Actions</h2>
      <p class=\"muted\">Use the CLI or the dashboard forms to add positions and alerts. The API endpoints are available under <span class=\"pill\">/api/*</span>.</p>
      <pre>{escape(json.dumps({"open_alerts": alerts_open, "pattern_examples": patterns, "quotes": len(snapshot.get('quotes', []))}, indent=2))}</pre>
    </section>
    """
    return _wrap_page("Trading Dashboard", body)


def _parse_form_body(body: bytes) -> dict[str, str]:
    parsed = parse_qs(body.decode("utf-8"))
    return {key: values[0] for key, values in parsed.items() if values}


def _parse_multipart_form(content_type: str, payload: bytes) -> tuple[dict[str, str], dict[str, tuple[str, bytes]]]:
    message = BytesParser(policy=email_default_policy).parsebytes(
        f"Content-Type: {content_type}\nMIME-Version: 1.0\n\n".encode("utf-8") + payload
    )

    fields: dict[str, str] = {}
    files: dict[str, tuple[str, bytes]] = {}

    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename()
        data = part.get_payload(decode=True) or b""
        if filename:
            files[name] = (filename, data)
        else:
            fields[name] = data.decode("utf-8", errors="replace")

    return fields, files


def _parse_request_form(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    content_type = handler.headers.get("Content-Type", "")
    content_length = int(handler.headers.get("Content-Length", "0"))
    payload = handler.rfile.read(content_length)

    if content_type.startswith("multipart/form-data"):
        fields, files = _parse_multipart_form(content_type, payload)
        return {**fields, **{key: filename for key, (filename, _) in files.items()}}

    return _parse_form_body(payload)


class DashboardRequestHandler(BaseHTTPRequestHandler):
    server_version = "TradingDashboard/1.0"

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, indent=2, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, html: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            import_message = parse_qs(parsed.query).get("import", [None])[0]
            self._send_html(_render_dashboard(import_message=import_message))
            return
        if parsed.path == "/api/snapshot":
            self._send_json(STATE.get())
            return
        if parsed.path == "/events":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            event_queue = EVENT_HUB.subscribe()
            try:
                while True:
                    snapshot = event_queue.get()
                    payload = f"data: {json.dumps(snapshot, default=str)}\n\n".encode("utf-8")
                    self.wfile.write(payload)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, KeyboardInterrupt):
                pass
            finally:
                EVENT_HUB.unsubscribe(event_queue)
            return
        if parsed.path == "/api/portfolio":
            self._send_json({"positions": list_positions(), "metrics": STATE.get().get("metrics", {})})
            return
        if parsed.path == "/api/alerts":
            self._send_json({"alerts": list_price_alerts()})
            return
        if parsed.path == "/api/quotes":
            self._send_json({"quotes": load_quotes()})
            return
        if parsed.path == "/api/compare":
            symbol = parse_qs(parsed.query).get("symbol", ["AAPL"])[0]
            self._send_json(compare_providers(symbol))
            return
        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        if parsed.path == "/portfolio/import-file":
            content_type = self.headers.get("Content-Type", "")
            if not content_type.startswith("multipart/form-data"):
                self._send_json({"error": "Upload requires multipart/form-data"}, status=HTTPStatus.BAD_REQUEST)
                return

            content_length = int(self.headers.get("Content-Length", "0"))
            payload = self.rfile.read(content_length)
            form_fields, file_fields = _parse_multipart_form(content_type, payload)
            upload = file_fields.get("portfolio_file")
            if upload is None:
                self._send_json({"error": "No portfolio file uploaded"}, status=HTTPStatus.BAD_REQUEST)
                return

            filename, file_bytes = upload
            import tempfile

            suffix = Path(filename).suffix.lower() or ".bin"
            if suffix == ".pdf":
                with tempfile.NamedTemporaryFile("wb", suffix=suffix, delete=False) as tmp:
                    tmp.write(file_bytes)
                    temp_path = Path(tmp.name)
            else:
                with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False, encoding="utf-8") as tmp:
                    tmp.write(file_bytes.decode("utf-8-sig", errors="replace"))
                    temp_path = Path(tmp.name)
            try:
                if suffix == ".pdf":
                    result = import_positions_from_pdf(temp_path, replace=form_fields.get("replace") == "1", source=form_fields.get("source", "other") or "other")
                else:
                    result = import_positions_from_csv(temp_path, replace=form_fields.get("replace") == "1", source=form_fields.get("source", "other") or "other")
            finally:
                temp_path.unlink(missing_ok=True)
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", f"/?import=Imported%20{result['imported']}%20rows%20from%20{result['format']}")
            self.end_headers()
            return

        form = _parse_request_form(self)

        if parsed.path == "/positions/add":
            add_position(
                form["symbol"],
                float(form["quantity"]),
                float(form["average_price"]),
                source=form.get("source", "manual"),
            )
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.end_headers()
            return

        if parsed.path == "/positions/update":
            update_position(int(form["position_id"]), form["symbol"], float(form["quantity"]), float(form["average_price"]))
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.end_headers()
            return

        if parsed.path == "/positions/delete":
            delete_position(int(form["position_id"]))
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.end_headers()
            return

        if parsed.path == "/alerts/add":
            create_price_alert(form["symbol"], form["operator"], float(form["target_price"]))
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.end_headers()
            return

        if parsed.path == "/alerts/update":
            update_price_alert(
                int(form["alert_id"]),
                form["symbol"],
                form["operator"],
                float(form["target_price"]),
                active=form.get("active", "1") == "1",
            )
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.end_headers()
            return

        if parsed.path == "/alerts/delete":
            delete_price_alert(int(form["alert_id"]))
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.end_headers()
            return

        if parsed.path == "/alerts/evaluate":
            triggered = evaluate_price_alerts(form["symbol"], float(form["current_price"]))
            self._send_json({"triggered": triggered})
            return

        if parsed.path == "/api/fetch":
            result = fetch_data(form["symbol"], provider=form.get("provider", "finnhub"), save_to_db=True)
            self._send_json({"result": result})
            return

        if parsed.path == "/api/backtest":
            prices = [float(value.strip()) for value in form["prices"].split(",") if value.strip()]
            self._send_json({"result": moving_average_crossover_backtest(prices)})
            return

        if parsed.path == "/api/patterns":
            candle_payload = json.loads(form["candles"])
            self._send_json({"patterns": detect_candlestick_patterns(candle_payload)})
            return

        if parsed.path == "/api/value":
            prices = {
                item.split("=", 1)[0].strip().upper(): float(item.split("=", 1)[1].strip())
                for item in form["prices"].split(",")
                if "=" in item
            }
            self._send_json({"result": portfolio_value(prices)})
            return

        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def create_dashboard_app() -> type[DashboardRequestHandler]:
    return DashboardRequestHandler


def run_dashboard_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    refresh_interval = max(int(get_provider_min_interval("finnhub")), int(get_provider_min_interval("alpha_vantage")), 15)
    worker = threading.Thread(target=_dashboard_worker, args=(refresh_interval,), daemon=True)
    worker.start()
    server = ThreadingHTTPServer((host, port), create_dashboard_app())
    print(f"Dashboard running on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down dashboard...")
    finally:
        server.server_close()