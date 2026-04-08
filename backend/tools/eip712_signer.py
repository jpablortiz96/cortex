"""
CORTEX — EIP-712 Typed Data Signer
Signs trade intents and risk attestations with the deployer private key.
Signatures are verifiable on-chain and off-chain by anyone.

Domain: CORTEX Trading Desk / v1 / Sepolia (chainId 11155111)
"""

import os
import time
from eth_account import Account
from eth_account.messages import encode_typed_data


# ─── EIP-712 Domain ──────────────────────────────────────────────────────────

DOMAIN = {
    "name": "CORTEX Trading Desk",
    "version": "1",
    "chainId": 11155111,
}

DOMAIN_TYPE = [
    {"name": "name",    "type": "string"},
    {"name": "version", "type": "string"},
    {"name": "chainId", "type": "uint256"},
]

# ─── Type Definitions ────────────────────────────────────────────────────────

# TradeIntent — signed by the Strategist after generating a proposal.
# Prices are stored as integers (USD * 100) to avoid floating-point issues.
TRADE_INTENT_TYPE = [
    {"name": "asset",       "type": "string"},   # e.g. "SOL"
    {"name": "side",        "type": "string"},   # "LONG" | "SHORT"
    {"name": "sizeUsd",     "type": "uint256"},  # size in USD cents
    {"name": "price",       "type": "uint256"},  # entry price in USD cents
    {"name": "stopLoss",    "type": "uint256"},  # stop loss in USD cents
    {"name": "takeProfit",  "type": "uint256"},  # take profit in USD cents
    {"name": "confidence",  "type": "uint256"},  # 0–10000 basis points (72% = 7200)
    {"name": "timestamp",   "type": "uint256"},  # unix timestamp (seconds)
    {"name": "agentId",     "type": "string"},   # e.g. "strategist"
]

# RiskAttestation — signed by the Risk Officer after evaluating a proposal.
RISK_ATTESTATION_TYPE = [
    {"name": "tradeId",    "type": "string"},   # proposal ID
    {"name": "decision",   "type": "string"},   # "APPROVED" | "VETOED"
    {"name": "riskScore",  "type": "uint256"},  # 0–100 (risk_score * 10)
    {"name": "reasoning",  "type": "string"},   # first 200 chars of reasoning
    {"name": "timestamp",  "type": "uint256"},  # unix timestamp
    {"name": "agentId",    "type": "string"},   # "risk_officer"
]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _to_cents(usd_float: float) -> int:
    """Convert a USD float to integer cents (2 decimal precision)."""
    return int(round(usd_float * 100))


def _to_bps(pct_float: float) -> int:
    """Convert a 0–1 float confidence to basis points (0–10000)."""
    return int(round(pct_float * 10000))


# ─── Signer ──────────────────────────────────────────────────────────────────

class EIP712Signer:
    """
    Signs CORTEX trading events with EIP-712 typed data signatures.
    The signer address is the deployer wallet (DEPLOYER_PRIVATE_KEY).
    """

    def __init__(self):
        pk = os.getenv("DEPLOYER_PRIVATE_KEY", "")
        if pk and not pk.startswith("0x"):
            pk = "0x" + pk
        self.private_key = pk
        self.enabled = bool(pk)
        if self.enabled:
            self.signer_address = Account.from_key(pk).address
        else:
            self.signer_address = ""

    def _sign(self, primary_type: str, type_def: list, message: dict) -> dict:
        """
        Core signing method. Returns a dict with:
          - signature: "0x..." hex string (65 bytes: r + s + v)
          - message_hash: "0x..." hex of the EIP-712 hash
          - signer: checksummed address
          - primary_type: the type name that was signed
        """
        if not self.enabled:
            return {}

        typed_data = {
            "types": {
                "EIP712Domain": DOMAIN_TYPE,
                primary_type: type_def,
            },
            "primaryType": primary_type,
            "domain": DOMAIN,
            "message": message,
        }

        signable = encode_typed_data(full_message=typed_data)
        signed = Account.sign_message(signable, private_key=self.private_key)

        return {
            "signature": "0x" + signed.signature.hex(),
            "message_hash": "0x" + signed.message_hash.hex(),
            "signer": self.signer_address,
            "primary_type": primary_type,
            "domain": f"{DOMAIN['name']} v{DOMAIN['version']} chainId={DOMAIN['chainId']}",
        }

    def sign_trade_intent(self, proposal: dict) -> dict:
        """
        Sign a trade proposal as a TradeIntent.
        Call after the Strategist generates a proposal.
        """
        message = {
            "asset":      proposal.get("asset", ""),
            "side":       proposal.get("side", ""),
            "sizeUsd":    _to_cents(proposal.get("size_usd", 0)),
            "price":      _to_cents(proposal.get("entry_price", 0)),
            "stopLoss":   _to_cents(proposal.get("stop_loss", 0)),
            "takeProfit": _to_cents(proposal.get("take_profit", 0)),
            "confidence": _to_bps(proposal.get("confidence", 0)),
            "timestamp":  int(time.time()),
            "agentId":    "strategist",
        }
        return self._sign("TradeIntent", TRADE_INTENT_TYPE, message)

    def sign_risk_attestation(self, assessment: dict) -> dict:
        """
        Sign a risk assessment as a RiskAttestation.
        Call after the Risk Officer evaluates a proposal.
        """
        message = {
            "tradeId":   assessment.get("proposal_id", ""),
            "decision":  assessment.get("decision", ""),
            "riskScore": int(round(assessment.get("risk_score", 0) * 10)),
            "reasoning": assessment.get("reasoning", "")[:200],
            "timestamp": int(time.time()),
            "agentId":   "risk_officer",
        }
        return self._sign("RiskAttestation", RISK_ATTESTATION_TYPE, message)

    def verify_trade_intent(self, proposal: dict, sig_data: dict) -> bool:
        """Recover signer from a TradeIntent signature and check it matches."""
        if not sig_data:
            return False
        try:
            message = {
                "asset":      proposal.get("asset", ""),
                "side":       proposal.get("side", ""),
                "sizeUsd":    _to_cents(proposal.get("size_usd", 0)),
                "price":      _to_cents(proposal.get("entry_price", 0)),
                "stopLoss":   _to_cents(proposal.get("stop_loss", 0)),
                "takeProfit": _to_cents(proposal.get("take_profit", 0)),
                "confidence": _to_bps(proposal.get("confidence", 0)),
                "timestamp":  sig_data.get("timestamp", int(time.time())),
                "agentId":    "strategist",
            }
            typed_data = {
                "types": {"EIP712Domain": DOMAIN_TYPE, "TradeIntent": TRADE_INTENT_TYPE},
                "primaryType": "TradeIntent",
                "domain": DOMAIN,
                "message": message,
            }
            signable = encode_typed_data(full_message=typed_data)
            recovered = Account.recover_message(signable, signature=sig_data["signature"])
            return recovered.lower() == self.signer_address.lower()
        except Exception:
            return False