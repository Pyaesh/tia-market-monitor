from flask import Flask, jsonify
import requests
import pandas as pd

app = Flask(__name__)


def get_klines(symbol, interval="4h", limit=300):
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }

    data = requests.get(url, params=params, timeout=10).json()

    columns = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "number_of_trades",
        "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"
    ]

    df = pd.DataFrame(data, columns=columns)

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")

    return df


def add_indicators(df):
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()

    rs = avg_gain / avg_loss
    df["rsi14"] = 100 - (100 / (1 + rs))

    df["ema12"] = df["close"].ewm(span=12, adjust=False).mean()
    df["ema26"] = df["close"].ewm(span=26, adjust=False).mean()

    df["macd"] = df["ema12"] - df["ema26"]
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    prev_close = df["close"].shift(1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr14"] = true_range.ewm(alpha=1/14, adjust=False).mean()

    return df


def analyze_symbol(symbol):
    df = get_klines(symbol)
    df = add_indicators(df)

    closed = df.iloc[-2]
    live = df.iloc[-1]

    avg_volume20 = df["volume"].iloc[-22:-2].mean()
    volume_ratio = closed["volume"] / avg_volume20

    score = 0
    notes = []

    if closed["close"] > closed["ema20"]:
        score += 1
        notes.append("Price above EMA20")
    else:
        score -= 1
        notes.append("Price below EMA20")

    if closed["ema20"] > closed["ema50"] > closed["ema200"]:
        score += 2
        notes.append("Bullish EMA structure")
    elif closed["ema20"] < closed["ema50"] < closed["ema200"]:
        score -= 2
        notes.append("Bearish EMA structure")

    if 50 <= closed["rsi14"] < 70:
        score += 1
        notes.append("Healthy bullish RSI")
    elif closed["rsi14"] >= 70:
        notes.append("RSI stretched")

    if closed["macd_hist"] > 0:
        score += 1
        notes.append("MACD momentum positive")
    else:
        score -= 1
        notes.append("MACD momentum cooling")

    if volume_ratio >= 1.5:
        score += 2
        notes.append("Strong volume confirmation")
    elif volume_ratio >= 1.0:
        score += 1
        notes.append("Healthy volume")
    elif volume_ratio < 0.7:
        score -= 1
        notes.append("Weak volume confirmation")

    return {
        "symbol": symbol,
        "closed_4h": {
            "time": str(closed["open_time"]),
            "open": round(closed["open"], 6),
            "high": round(closed["high"], 6),
            "low": round(closed["low"], 6),
            "close": round(closed["close"], 6),
            "volume": round(closed["volume"], 2)
        },
        "live_4h": {
            "time": str(live["open_time"]),
            "price": round(live["close"], 6),
            "high": round(live["high"], 6),
            "low": round(live["low"], 6),
            "volume": round(live["volume"], 2)
        },
        "indicators": {
            "ema20": round(closed["ema20"], 6),
            "ema50": round(closed["ema50"], 6),
            "ema200": round(closed["ema200"], 6),
            "rsi14": round(closed["rsi14"], 2),
            "macd": round(closed["macd"], 6),
            "macd_signal": round(closed["macd_signal"], 6),
            "macd_hist": round(closed["macd_hist"], 6),
            "atr14": round(closed["atr14"], 6),
            "volume_ratio": round(volume_ratio, 2)
        },
        "score": score,
        "notes": notes
    }


@app.route("/")
def home():
    return jsonify({
        "status": "ok",
        "message": "TIA market monitor is running"
    })


@app.route("/report")
def report():
    tia = analyze_symbol("TIAUSDT")
    btc = analyze_symbol("BTCUSDT")
    eth = analyze_symbol("ETHUSDT")

    market_score = btc["score"] + eth["score"]

    if market_score >= 6:
        market_status = "SUPPORTIVE"
    elif market_score >= 3:
        market_status = "MILDLY SUPPORTIVE"
    elif market_score >= 0:
        market_status = "NEUTRAL"
    else:
        market_status = "RISKY"

    return jsonify({
        "market_status": market_status,
        "TIA": tia,
        "BTC": btc,
        "ETH": eth
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
