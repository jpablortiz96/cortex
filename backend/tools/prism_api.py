"""
CORTEX — PRISM API Client (Strykr)
AI-powered market intelligence: prices, signals, and risk metrics.
Used as supplemental intelligence alongside Kraken CLI market data.

Docs: https://api.prismapi.ai/docs
Partner: Strykr / PRISM (hackathon technology partner)
"""

import os
import asyncio
import httpx
from typing import Optional

BASE_URL = "https://api.prismapi.ai"
TIMEOUT = 8.0


def _get_api_key() -> str:
    return os.getenv("PRISM_API_KEY", "")


def _headers() -> dict:
    return {"X-API-Key": _get_api_key()}


# ─── Price ────────────────────────────────────────────────────────────────────

async def get_price(symbol: str) -> Optional[dict]:
    """
    GET /crypto/price/{symbol}
    Returns price_usd, change_24h_pct, volume_24h, confidence.
    """
    key = _get_api_key()
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(f"{BASE_URL}/crypto/price/{symbol}", headers=_headers())
            r.raise_for_status()
            d = r.json()
            return {
                "price_usd": d.get("price_usd"),
                "change_24h_pct": d.get("change_24h_pct"),
                "volume_24h": d.get("volume_24h"),
                "confidence": d.get("confidence"),
                "source": "prism",
            }
    except Exception:
        return None


# ─── Signals ─────────────────────────────────────────────────────────────────

async def get_signals(symbol: str) -> Optional[dict]:
    """
    GET /signals/{symbol}
    Returns overall_signal, direction, strength, bullish/bearish scores,
    active_signals list, and key technical indicators (RSI, MACD, Bollinger).
    """
    key = _get_api_key()
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(f"{BASE_URL}/signals/{symbol}", headers=_headers())
            r.raise_for_status()
            d = r.json()
            data_list = d.get("data", [])
            if not data_list:
                return None
            item = data_list[0]
            indicators = item.get("indicators", {})
            active = item.get("active_signals", [])
            return {
                "overall_signal": item.get("overall_signal", "neutral"),
                "direction": item.get("direction", "neutral"),
                "strength": item.get("strength", "weak"),
                "bullish_score": item.get("bullish_score", 0),
                "bearish_score": item.get("bearish_score", 0),
                "net_score": item.get("net_score", 0),
                "rsi": indicators.get("rsi"),
                "macd_histogram": indicators.get("macd_histogram"),
                "bollinger_upper": indicators.get("bollinger_upper"),
                "bollinger_lower": indicators.get("bollinger_lower"),
                "active_signals": [s.get("type") for s in active],
                "signal_count": item.get("signal_count", 0),
                "source": "prism",
            }
    except Exception:
        return None


# ─── Risk ─────────────────────────────────────────────────────────────────────

async def get_risk(symbol: str) -> Optional[dict]:
    """
    GET /risk/{symbol}
    Returns volatility, sharpe ratio, max drawdown, positive_days_pct.
    """
    key = _get_api_key()
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(f"{BASE_URL}/risk/{symbol}", headers=_headers())
            r.raise_for_status()
            d = r.json()
            return {
                "daily_volatility": d.get("daily_volatility"),
                "annual_volatility": d.get("annual_volatility"),
                "sharpe_ratio": d.get("sharpe_ratio"),
                "sortino_ratio": d.get("sortino_ratio"),
                "max_drawdown": d.get("max_drawdown"),
                "current_drawdown": d.get("current_drawdown"),
                "positive_days_pct": d.get("positive_days_pct"),
                "period_days": d.get("period_days", 90),
                "source": "prism",
            }
    except Exception:
        return None


# ─── Combined intelligence for one asset ─────────────────────────────────────

async def get_asset_intelligence(symbol: str) -> dict:
    """
    Fetch signals + risk in parallel for one asset.
    Returns a dict with prism_signal and prism_risk keys (both optional).
    Gracefully returns empty dict if API is unavailable.
    """
    signals, risk = await asyncio.gather(
        get_signals(symbol),
        get_risk(symbol),
        return_exceptions=True,
    )
    result = {}
    if isinstance(signals, dict):
        result["prism_signal"] = signals
    if isinstance(risk, dict):
        result["prism_risk"] = risk
    return result


# ─── Batch for all CORTEX assets ─────────────────────────────────────────────

async def get_all_intelligence(assets: list[str] = None) -> dict:
    """
    Fetch PRISM intelligence for BTC, ETH, SOL in parallel.
    Returns {asset: {prism_signal: ..., prism_risk: ...}, ...}
    Any failures are silently omitted — PRISM is supplemental.
    """
    if assets is None:
        assets = ["BTC", "ETH", "SOL"]

    if not _get_api_key():
        return {}

    results = await asyncio.gather(
        *[get_asset_intelligence(a) for a in assets],
        return_exceptions=True,
    )

    output = {}
    for asset, result in zip(assets, results):
        if isinstance(result, dict) and result:
            output[asset] = result

    return output


# ─── Quick test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    async def test():
        print("Testing PRISM API...\n")
        intel = await get_all_intelligence()
        print(json.dumps(intel, indent=2))

    asyncio.run(test())
