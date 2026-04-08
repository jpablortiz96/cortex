"""
CORTEX — Market Data Provider
Fetches real-time market data from Kraken public API.
No API key needed for public market data.
"""

import asyncio
import json
import subprocess
import httpx
from datetime import datetime
from typing import Optional
from tools.prism_api import get_all_intelligence as get_prism_intelligence

KRAKEN_CLI_TICKER_PAIRS = {"BTC": "XBTUSD", "ETH": "ETHUSD", "SOL": "SOLUSD"}
KRAKEN_CLI_RESPONSE_KEYS = {"BTC": "XXBTZUSD", "ETH": "XETHZUSD", "SOL": "SOLUSD"}


# Kraken pair mappings
KRAKEN_PAIRS = {
    "BTC": "XXBTZUSD",
    "ETH": "XETHZUSD",
    "SOL": "SOLUSD",
}

KRAKEN_OHLC_PAIRS = {
    "BTC": "XBTUSD",
    "ETH": "ETHUSD",
    "SOL": "SOLUSD",
}


async def fetch_kraken_ticker(assets: list[str] = None) -> dict:
    """
    Fetch real-time ticker data from Kraken public API.
    Returns price, volume, and 24h change for each asset.
    """
    if assets is None:
        assets = ["BTC", "ETH", "SOL"]

    pairs = [KRAKEN_PAIRS[a] for a in assets if a in KRAKEN_PAIRS]
    pair_string = ",".join(pairs)

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                f"https://api.kraken.com/0/public/Ticker?pair={pair_string}"
            )
            response.raise_for_status()
            data = response.json()

            if data.get("error") and len(data["error"]) > 0:
                print(f"[WARN] Kraken API warning: {data['error']}")

            result = data.get("result", {})
            market_data = {}

            for asset in assets:
                pair_key = KRAKEN_PAIRS.get(asset)
                if pair_key and pair_key in result:
                    ticker = result[pair_key]
                    # Kraken ticker fields:
                    # a = ask [price, whole lot volume, lot volume]
                    # b = bid [price, whole lot volume, lot volume]
                    # c = last trade closed [price, lot volume]
                    # v = volume [today, last 24h]
                    # p = vwap [today, last 24h]
                    # t = number of trades [today, last 24h]
                    # l = low [today, last 24h]
                    # h = high [today, last 24h]
                    # o = today's opening price

                    price = float(ticker["c"][0])
                    open_price = float(ticker["o"])
                    high_24h = float(ticker["h"][1])
                    low_24h = float(ticker["l"][1])
                    volume_24h = float(ticker["v"][1])
                    vwap_24h = float(ticker["p"][1])

                    change_24h_pct = ((price - open_price) / open_price * 100) if open_price > 0 else 0

                    # Calculate simple volatility from high-low range
                    volatility = ((high_24h - low_24h) / price * 100) if price > 0 else 0

                    market_data[asset] = {
                        "price": round(price, 2),
                        "open": round(open_price, 2),
                        "high_24h": round(high_24h, 2),
                        "low_24h": round(low_24h, 2),
                        "change_24h_pct": round(change_24h_pct, 2),
                        "volume_24h": round(volume_24h * price, 0),  # Convert to USD
                        "vwap_24h": round(vwap_24h, 2),
                        "volatility_24h": round(volatility, 2),
                    }

            return market_data

        except httpx.HTTPError as e:
            print(f"[ERROR] Kraken API error: {e}")
            return {}
        except Exception as e:
            print(f"[ERROR] Market data error: {e}")
            return {}


async def fetch_kraken_ohlc(asset: str, interval: int = 60) -> list[dict]:
    """
    Fetch OHLC (candlestick) data for RSI calculation.
    interval: minutes (1, 5, 15, 30, 60, 240, 1440, 10080, 21600)
    Returns last 50 candles.
    """
    pair = KRAKEN_OHLC_PAIRS.get(asset)
    if not pair:
        return []

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval={interval}"
            )
            response.raise_for_status()
            data = response.json()
            result = data.get("result", {})

            # Find the data key (varies by pair)
            candles_raw = None
            for key in result:
                if key != "last":
                    candles_raw = result[key]
                    break

            if not candles_raw:
                return []

            # Parse candles: [time, open, high, low, close, vwap, volume, count]
            candles = []
            for c in candles_raw[-50:]:  # Last 50 candles
                candles.append({
                    "time": int(c[0]),
                    "open": float(c[1]),
                    "high": float(c[2]),
                    "low": float(c[3]),
                    "close": float(c[4]),
                    "vwap": float(c[5]),
                    "volume": float(c[6]),
                })

            return candles

        except Exception as e:
            print(f"[ERROR] OHLC error for {asset}: {e}")
            return []


def calculate_rsi(candles: list[dict], period: int = 14) -> Optional[float]:
    """Calculate RSI from OHLC candle data."""
    if len(candles) < period + 1:
        return None

    closes = [c["close"] for c in candles]
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]

    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Smoothed RSI
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 1)


async def get_full_market_data(assets: list[str] = None) -> dict:
    """
    Get complete market data with ticker + RSI for all assets.
    This is what the Orchestrator calls each cycle.
    """
    if assets is None:
        assets = ["BTC", "ETH", "SOL"]

    # Try Kraken CLI first (primary), fall back to REST API
    ticker_data = await fetch_kraken_cli_ticker(assets)
    source = "kraken-cli"
    if not ticker_data:
        ticker_data = await fetch_kraken_ticker(assets)
        source = "kraken_public_api"

    # Fetch OHLC + RSI and PRISM intelligence in parallel
    ohlc_tasks = [fetch_kraken_ohlc(a, interval=60) for a in assets]
    ohlc_results, prism_data = await asyncio.gather(
        asyncio.gather(*ohlc_tasks),
        get_prism_intelligence(assets),
        return_exceptions=True,
    )

    prism_data = prism_data if isinstance(prism_data, dict) else {}

    for i, asset in enumerate(assets):
        if asset not in ticker_data:
            continue

        # RSI from OHLC
        candles = ohlc_results[i] if isinstance(ohlc_results, (list, tuple)) else []
        rsi = calculate_rsi(candles) if candles else None
        ticker_data[asset]["rsi_14"] = rsi if rsi is not None else 50.0

        # Momentum: price vs VWAP
        price = ticker_data[asset]["price"]
        vwap = ticker_data[asset].get("vwap_24h", 0)
        ticker_data[asset]["price_vs_vwap_pct"] = (
            round((price - vwap) / vwap * 100, 3) if vwap > 0 else 0
        )

        # PRISM intelligence (supplemental — omit if unavailable)
        if asset in prism_data:
            intel = prism_data[asset]
            signal = intel.get("prism_signal", {})
            risk = intel.get("prism_risk", {})
            if signal:
                ticker_data[asset]["prism_signal"] = signal.get("overall_signal", "neutral")
                ticker_data[asset]["prism_strength"] = signal.get("strength", "")
                ticker_data[asset]["prism_net_score"] = signal.get("net_score", 0)
                ticker_data[asset]["prism_active_signals"] = signal.get("active_signals", [])
            if risk:
                ticker_data[asset]["prism_sharpe"] = risk.get("sharpe_ratio")
                ticker_data[asset]["prism_max_drawdown"] = risk.get("max_drawdown")
                ticker_data[asset]["prism_annual_vol"] = risk.get("annual_volatility")

    has_prism = any("prism_signal" in ticker_data.get(a, {}) for a in assets)
    sources = f"{source}+prism" if has_prism else source

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "source": sources,
        "assets": ticker_data,
    }



async def fetch_kraken_cli_ticker(assets: list = None) -> dict:
    if assets is None:
        assets = ["BTC", "ETH", "SOL"]
    pairs = [KRAKEN_CLI_TICKER_PAIRS[a] for a in assets if a in KRAKEN_CLI_TICKER_PAIRS]
    cmd = ["kraken", "ticker"] + pairs + ["-o", "json"]
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=15),
        )
        if result.returncode != 0:
            return {}
        raw = json.loads(result.stdout)
        market_data = {}
        for asset in assets:
            rkey = KRAKEN_CLI_RESPONSE_KEYS.get(asset)
            if not rkey or rkey not in raw:
                continue
            t = raw[rkey]
            price = float(t["c"][0])
            open_p = float(t["o"])
            h24 = float(t["h"][1])
            l24 = float(t["l"][1])
            vol24 = float(t["v"][1])
            vwap = float(t["p"][1])
            chg = ((price - open_p) / open_p * 100) if open_p > 0 else 0
            volat = ((h24 - l24) / price * 100) if price > 0 else 0
            market_data[asset] = {
                "price": round(price, 2),
                "open": round(open_p, 2),
                "high_24h": round(h24, 2),
                "low_24h": round(l24, 2),
                "change_24h_pct": round(chg, 2),
                "volume_24h": round(vol24 * price, 0),
                "vwap_24h": round(vwap, 2),
                "volatility_24h": round(volat, 2),
                "source": "kraken-cli",
            }
        return market_data
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        return {}
# Quick test
if __name__ == "__main__":
    async def test():
        print("Fetching real market data from Kraken...\n")
        data = await get_full_market_data()
        import json
        print(json.dumps(data, indent=2))

    asyncio.run(test())
