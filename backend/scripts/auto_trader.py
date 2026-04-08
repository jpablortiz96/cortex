"""
CORTEX — Auto Trader (24/7 hackathon intent blaster)
Sends 1 TradeIntent every 7 minutes = ~8-9/hour, staying under the 10/hour cap.

Usage:
  python backend/scripts/auto_trader.py

Environment:
  DEPLOYER_PRIVATE_KEY  — wallet private key
  SEPOLIA_RPC           — optional override RPC URL
  AGENT_ID              — optional override (default 46)
"""

import os
import sys
import time
import json
import random
import logging
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from tools.hackathon_client import HackathonClient

# ── Config ────────────────────────────────────────────────────────────────────
AGENT_FILE   = os.path.join(os.path.dirname(__file__), "..", "hackathon_agent.json")
LOG_FILE     = os.path.join(os.path.dirname(__file__), "..", "auto_trader.log")
INTERVAL_SEC = 420          # 7 minutes between intents (8.5/hour, safely under 10)
AGENT_ID     = int(os.getenv("AGENT_ID", "46"))

# Trade rotation — varied assets, sides, amounts
TRADE_ROTATION = [
    ("XBTUSD", "BUY",  100.0),
    ("ETHUSD", "SELL", 150.0),
    ("SOLUSD", "BUY",  200.0),
    ("XBTUSD", "SELL", 300.0),
    ("ETHUSD", "BUY",  250.0),
    ("SOLUSD", "SELL", 100.0),
    ("XBTUSD", "BUY",  500.0),
    ("ETHUSD", "SELL", 200.0),
    ("SOLUSD", "BUY",  150.0),
    ("XBTUSD", "SELL", 400.0),
    ("ETHUSD", "BUY",  300.0),
    ("SOLUSD", "SELL", 250.0),
]

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("auto_trader")


def load_agent_id() -> int:
    if os.path.exists(AGENT_FILE):
        with open(AGENT_FILE) as f:
            return json.load(f).get("agent_id", AGENT_ID)
    return AGENT_ID


def run():
    agent_id = load_agent_id()
    log.info(f"Starting auto_trader | agent_id={agent_id} | interval={INTERVAL_SEC}s")

    client    = None
    idx       = 0
    total_ok  = 0
    total_err = 0

    while True:
        # Re-init client if needed (handles RPC flakes)
        if client is None:
            try:
                client = HackathonClient()
                log.info(f"Client initialized | wallet={client.account.address}")
            except Exception as e:
                log.error(f"Client init failed: {e} — retrying in 60s")
                time.sleep(60)
                continue

        pair, action, amount = TRADE_ROTATION[idx % len(TRADE_ROTATION)]
        idx += 1

        try:
            # Check remaining capacity in current 1-hour window
            record = client.router.functions.getTradeRecord(agent_id).call()
            count_in_window = record[0]
            window_start    = record[1]
            now             = int(time.time())
            window_age      = now - window_start if window_start > 0 else 3600

            if window_age >= 3600:
                # New window — reset
                remaining = 10
            else:
                remaining = max(0, 10 - count_in_window)

            if remaining == 0:
                wait = 3600 - window_age + 10
                log.info(f"Hour cap reached — waiting {wait}s for new window")
                time.sleep(wait)
                continue

            # Submit intent
            result = client.submit_trade_intent(agent_id, pair, action, amount)
            total_ok += 1
            log.info(
                f"[{total_ok}] INTENT OK | {action} {pair} ${amount} "
                f"| nonce={result['nonce']} total={result['total_trades']} "
                f"| tx={result['tx_hash'][:20]}..."
            )

        except Exception as e:
            total_err += 1
            err_str = str(e)
            log.error(f"Intent failed ({total_err} total): {err_str[:120]}")

            # Reset client on connection errors
            if any(kw in err_str.lower() for kw in ["connection", "timeout", "rpc", "network"]):
                log.warning("RPC error — resetting client")
                client = None

            time.sleep(30)
            continue

        # Stats every 10 intents
        if total_ok % 10 == 0:
            try:
                stats = client.get_stats(agent_id)
                log.info(f"STATS | {stats}")
            except Exception:
                pass

        log.info(f"Sleeping {INTERVAL_SEC}s...")
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    run()