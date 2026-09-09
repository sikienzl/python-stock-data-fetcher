from __future__ import annotations


def detect_candlestick_patterns(ohlc: list[dict]) -> list[dict]:
    patterns: list[dict] = []
    for candle in ohlc:
        open_price = float(candle["o"])
        close_price = float(candle["c"])
        high_price = float(candle["h"])
        low_price = float(candle["l"])
        body = abs(close_price - open_price)
        upper_shadow = high_price - max(open_price, close_price)
        lower_shadow = min(open_price, close_price) - low_price

        if body <= (high_price - low_price) * 0.25 and lower_shadow > body * 2 and upper_shadow <= body:
            patterns.append({"pattern": "hammer", "date": candle.get("t"), "symbol": candle.get("symbol")})
        elif body <= (high_price - low_price) * 0.1:
            patterns.append({"pattern": "doji", "date": candle.get("t"), "symbol": candle.get("symbol")})

    return patterns