"""
CORTEX — Official Hackathon Contract Client
Integrates with the official AI Trading Agents hackathon contracts on Sepolia.

Contracts:
  AgentRegistry:      0x97b07dDc405B0c28B17559aFFE63BdB3632d0ca3
  HackathonVault:     0x0E7CD8ef9743FEcf94f9103033a044caBD45fC90
  RiskRouter:         0xd6A6952545FF6E6E6681c2d15C59f9EB8F40FdBC
  ValidationRegistry: 0x92bF63E5C7Ac6980f237a7164Ab413BE226187F1
  ReputationRegistry: 0x423a9904e39537a9997fbaF0f220d79D7d545763
"""

import os
import json
import hashlib
import time
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_typed_data

# ── Contract addresses ────────────────────────────────────────────────────────
AGENT_REGISTRY      = "0x97b07dDc405B0c28B17559aFFE63BdB3632d0ca3"
HACKATHON_VAULT     = "0x0E7CD8ef9743FEcf94f9103033a044caBD45fC90"
RISK_ROUTER         = "0xd6A6952545FF6E6E6681c2d15C59f9EB8F40FdBC"
VALIDATION_REGISTRY = "0x92bF63E5C7Ac6980f237a7164Ab413BE226187F1"
REPUTATION_REGISTRY = "0x423a9904e39537a9997fbaF0f220d79D7d545763"

# ── Minimal ABIs ──────────────────────────────────────────────────────────────
AGENT_REGISTRY_ABI = [
    {
        "name": "register",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "agentWallet",   "type": "address"},
            {"name": "name",          "type": "string"},
            {"name": "description",   "type": "string"},
            {"name": "capabilities",  "type": "string[]"},
            {"name": "agentURI",      "type": "string"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "getAgent",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "agentId", "type": "uint256"}],
        "outputs": [
            {"name": "operatorWallet", "type": "address"},
            {"name": "agentWallet",    "type": "address"},
            {"name": "name",           "type": "string"},
            {"name": "description",    "type": "string"},
            {"name": "capabilities",   "type": "string[]"},
            {"name": "registeredAt",   "type": "uint256"},
            {"name": "active",         "type": "bool"},
        ],
    },
    {
        "name": "getSigningNonce",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "agentId", "type": "uint256"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "totalAgents",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True,  "name": "agentId",       "type": "uint256"},
            {"indexed": True,  "name": "operatorWallet", "type": "address"},
            {"indexed": True,  "name": "agentWallet",    "type": "address"},
            {"indexed": False, "name": "name",           "type": "string"},
        ],
        "name": "AgentRegistered",
        "type": "event",
    },
]

VAULT_ABI = [
    {
        "name": "claimAllocation",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "agentId", "type": "uint256"}],
        "outputs": [],
    },
    {
        "name": "getBalance",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "agentId", "type": "uint256"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "hasClaimed",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "", "type": "uint256"}],
        "outputs": [{"name": "", "type": "bool"}],
    },
]

RISK_ROUTER_ABI = [
    {
        "name": "setRiskParams",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "agentId",              "type": "uint256"},
            {"name": "maxPositionUsdScaled", "type": "uint256"},
            {"name": "maxDrawdownBps",       "type": "uint256"},
            {"name": "maxTradesPerHour",     "type": "uint256"},
        ],
        "outputs": [],
    },
    {
        "name": "submitTradeIntent",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {
                "name": "intent",
                "type": "tuple",
                "components": [
                    {"name": "agentId",              "type": "uint256"},
                    {"name": "agentWallet",          "type": "address"},
                    {"name": "pair",                 "type": "string"},
                    {"name": "action",               "type": "string"},
                    {"name": "amountUsdScaled",      "type": "uint256"},
                    {"name": "maxSlippageBps",       "type": "uint256"},
                    {"name": "nonce",                "type": "uint256"},
                    {"name": "deadline",             "type": "uint256"},
                ],
            },
            {"name": "signature", "type": "bytes"},
        ],
        "outputs": [
            {"name": "approved", "type": "bool"},
            {"name": "reason",   "type": "string"},
        ],
    },
    {
        "name": "getIntentNonce",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "agentId", "type": "uint256"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "getTradeRecord",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "agentId", "type": "uint256"}],
        "outputs": [
            {"name": "count",       "type": "uint256"},
            {"name": "windowStart", "type": "uint256"},
        ],
    },
    {
        "name": "simulateIntent",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {
                "name": "intent",
                "type": "tuple",
                "components": [
                    {"name": "agentId",         "type": "uint256"},
                    {"name": "agentWallet",     "type": "address"},
                    {"name": "pair",            "type": "string"},
                    {"name": "action",          "type": "string"},
                    {"name": "amountUsdScaled", "type": "uint256"},
                    {"name": "maxSlippageBps",  "type": "uint256"},
                    {"name": "nonce",           "type": "uint256"},
                    {"name": "deadline",        "type": "uint256"},
                ],
            },
        ],
        "outputs": [
            {"name": "approved", "type": "bool"},
            {"name": "reason",   "type": "string"},
        ],
    },
]

VALIDATION_ABI = [
    {
        "name": "postEIP712Attestation",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "agentId",        "type": "uint256"},
            {"name": "checkpointHash", "type": "bytes32"},
            {"name": "score",          "type": "uint8"},
            {"name": "notes",          "type": "string"},
        ],
        "outputs": [],
    },
    {
        "name": "getAverageValidationScore",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "agentId", "type": "uint256"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "openValidation",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "bool"}],
    },
]

REPUTATION_ABI = [
    {
        "name": "submitFeedback",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "agentId",      "type": "uint256"},
            {"name": "score",        "type": "uint8"},
            {"name": "outcomeRef",   "type": "bytes32"},
            {"name": "comment",      "type": "string"},
            {"name": "feedbackType", "type": "uint8"},
        ],
        "outputs": [],
    },
    {
        "name": "getAverageScore",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "agentId", "type": "uint256"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]

# ── EIP-712 type data ─────────────────────────────────────────────────────────
TRADE_INTENT_TYPES = {
    "EIP712Domain": [
        {"name": "name",              "type": "string"},
        {"name": "version",           "type": "string"},
        {"name": "chainId",           "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "TradeIntent": [
        {"name": "agentId",          "type": "uint256"},
        {"name": "agentWallet",      "type": "address"},
        {"name": "pair",             "type": "string"},
        {"name": "action",           "type": "string"},
        {"name": "amountUsdScaled",  "type": "uint256"},
        {"name": "maxSlippageBps",   "type": "uint256"},
        {"name": "nonce",            "type": "uint256"},
        {"name": "deadline",         "type": "uint256"},
    ],
}

RISK_ROUTER_DOMAIN = {
    "name":              "RiskRouter",
    "version":           "1",
    "chainId":           11155111,
    "verifyingContract": RISK_ROUTER,
}


class HackathonClient:
    def __init__(self):
        rpc = os.getenv("SEPOLIA_RPC", "https://ethereum-sepolia-rpc.publicnode.com")
        self.w3 = Web3(Web3.HTTPProvider(rpc))
        pk = os.getenv("DEPLOYER_PRIVATE_KEY", "")
        if not pk:
            raise RuntimeError("DEPLOYER_PRIVATE_KEY not set")
        self.account = Account.from_key(pk)

        self.registry   = self.w3.eth.contract(address=Web3.to_checksum_address(AGENT_REGISTRY),      abi=AGENT_REGISTRY_ABI)
        self.vault      = self.w3.eth.contract(address=Web3.to_checksum_address(HACKATHON_VAULT),      abi=VAULT_ABI)
        self.router     = self.w3.eth.contract(address=Web3.to_checksum_address(RISK_ROUTER),          abi=RISK_ROUTER_ABI)
        self.validation = self.w3.eth.contract(address=Web3.to_checksum_address(VALIDATION_REGISTRY),  abi=VALIDATION_ABI)
        self.reputation = self.w3.eth.contract(address=Web3.to_checksum_address(REPUTATION_REGISTRY),  abi=REPUTATION_ABI)

        print(f"[HACKATHON] Wallet: {self.account.address}")
        print(f"[HACKATHON] Connected to Sepolia: {self.w3.is_connected()}")

    # ── Internal tx sender ────────────────────────────────────────────────────
    def _send(self, fn, gas: int = 300_000) -> str:
        nonce = self.w3.eth.get_transaction_count(self.account.address, "pending")
        block = self.w3.eth.get_block("latest")
        base_fee = block.get("baseFeePerGas", Web3.to_wei(10, "gwei"))
        max_fee  = base_fee * 3 + Web3.to_wei(2, "gwei")
        try:
            gas = fn.estimate_gas({"from": self.account.address}) + 50_000
        except Exception:
            pass  # use caller-provided gas
        tx = fn.build_transaction({
            "from":                 self.account.address,
            "nonce":                nonce,
            "gas":                  gas,
            "maxFeePerGas":         max_fee,
            "maxPriorityFeePerGas": Web3.to_wei(2, "gwei"),
            "chainId":              11155111,
        })
        signed  = self.w3.eth.account.sign_transaction(tx, self.account.key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt.status != 1:
            raise RuntimeError(f"Tx reverted: {tx_hash.hex()}")
        return tx_hash.hex()

    # ── Registration ──────────────────────────────────────────────────────────
    def register_agent(self) -> dict:
        """Register CORTEX in the official hackathon AgentRegistry."""
        name        = "CORTEX"
        description = "Autonomous multi-agent trading desk. Strategist + Risk Officer + Executor + Compliance + Auditor pipeline with EIP-712 signed intents."
        capabilities = ["market-analysis", "risk-management", "trade-execution", "on-chain-audit", "eip712-signing"]
        agent_uri   = "https://web-production-df8ac.up.railway.app/api/agents/strategist/metadata"
        agent_wallet = self.account.address  # operator == agent wallet (same key)

        print(f"[HACKATHON] Registering CORTEX in AgentRegistry...")
        tx_hash = self._send(
            self.registry.functions.register(agent_wallet, name, description, capabilities, agent_uri),
            gas=400_000,
        )

        # Get agentId from AgentRegistered event
        receipt = self.w3.eth.get_transaction_receipt(tx_hash)
        agent_id = None
        topic = self.w3.keccak(text="AgentRegistered(uint256,address,address,string)")
        for log in receipt.logs:
            if log.topics and log.topics[0] == topic:
                agent_id = int(log.topics[1].hex(), 16)
                break

        print(f"[HACKATHON] Registered! agent_id={agent_id} tx={tx_hash}")
        return {"agent_id": agent_id, "tx_hash": tx_hash}

    # ── Vault ─────────────────────────────────────────────────────────────────
    def claim_allocation(self, agent_id: int) -> str:
        """Claim 0.05 ETH sandbox capital from HackathonVault."""
        claimed = self.vault.functions.hasClaimed(agent_id).call()
        if claimed:
            print(f"[HACKATHON] agent_id={agent_id} already claimed allocation")
            return ""
        print(f"[HACKATHON] Claiming 0.05 ETH allocation for agent_id={agent_id}...")
        tx = self._send(self.vault.functions.claimAllocation(agent_id), gas=200_000)
        print(f"[HACKATHON] Claimed! tx={tx}")
        return tx

    # ── Risk params ───────────────────────────────────────────────────────────
    def set_risk_params(self, agent_id: int) -> str:
        """
        Set risk params in RiskRouter for our agent.
        maxPositionUsdScaled: 50000 = $500 (scaled x100)
        maxDrawdownBps: 500 = 5%
        maxTradesPerHour: 10
        """
        print(f"[HACKATHON] Setting risk params for agent_id={agent_id}...")
        tx = self._send(
            self.router.functions.setRiskParams(agent_id, 50000, 500, 10),
            gas=200_000,
        )
        print(f"[HACKATHON] Risk params set! tx={tx}")
        return tx

    # ── Trade Intent ──────────────────────────────────────────────────────────
    def _sign_trade_intent(self, intent: dict) -> bytes:
        """EIP-712 sign a TradeIntent struct."""
        structured_data = {
            "types":       TRADE_INTENT_TYPES,
            "domain":      RISK_ROUTER_DOMAIN,
            "primaryType": "TradeIntent",
            "message":     intent,
        }
        encoded  = encode_typed_data(full_message=structured_data)
        signed   = self.account.sign_message(encoded)
        return signed.signature

    def submit_trade_intent(self, agent_id: int, pair: str, action: str,
                             amount_usd: float = 100.0) -> dict:
        """
        Build, sign and submit a TradeIntent to the RiskRouter.
        action: 'BUY' or 'SELL'
        amount_usd: dollar amount (will be scaled x100)
        """
        nonce    = self.router.functions.getIntentNonce(agent_id).call()
        deadline = int(time.time()) + 300  # 5 min

        intent = {
            "agentId":         agent_id,
            "agentWallet":     self.account.address,
            "pair":            pair,
            "action":          action,
            "amountUsdScaled": int(amount_usd * 100),
            "maxSlippageBps":  50,
            "nonce":           nonce,
            "deadline":        deadline,
        }

        sig = self._sign_trade_intent(intent)

        # Convert intent to tuple form for ABI
        intent_tuple = (
            intent["agentId"],
            Web3.to_checksum_address(intent["agentWallet"]),
            intent["pair"],
            intent["action"],
            intent["amountUsdScaled"],
            intent["maxSlippageBps"],
            intent["nonce"],
            intent["deadline"],
        )

        print(f"[HACKATHON] Submitting TradeIntent: {action} {pair} ${amount_usd} nonce={nonce}...")
        tx_hash = self._send(
            self.router.functions.submitTradeIntent(intent_tuple, sig),
            gas=300_000,
        )
        print(f"[HACKATHON] Intent submitted! tx={tx_hash}")

        record = self.router.functions.getTradeRecord(agent_id).call()
        return {
            "tx_hash":      tx_hash,
            "action":       action,
            "pair":         pair,
            "amount_usd":   amount_usd,
            "nonce":        nonce,
            "total_trades": record[0],
            "explorer":     f"https://sepolia.etherscan.io/tx/{tx_hash}",
        }

    # ── Validation checkpoint ─────────────────────────────────────────────────
    def post_checkpoint(self, agent_id: int, action: str, asset: str,
                         reasoning: str, score: int = 80) -> str:
        """Post a validation checkpoint to ValidationRegistry."""
        checkpoint_hash = Web3.keccak(
            text=f"{agent_id}:{action}:{asset}:{int(time.time())}:{reasoning[:64]}"
        )
        notes = f"CORTEX {action} {asset} — {reasoning[:120]}"
        print(f"[HACKATHON] Posting validation checkpoint: {action} {asset} score={score}...")
        tx = self._send(
            self.validation.functions.postEIP712Attestation(
                agent_id, checkpoint_hash, score, notes
            ),
            gas=200_000,
        )
        print(f"[HACKATHON] Checkpoint posted! tx={tx}")
        return tx

    # ── Reputation ────────────────────────────────────────────────────────────
    def submit_reputation(self, agent_id: int, score: int, comment: str,
                           outcome_ref: bytes = None) -> str:
        """Submit self-feedback to ReputationRegistry. feedbackType=0 (TRADE_EXECUTION)."""
        if outcome_ref is None:
            outcome_ref = Web3.keccak(text=f"{agent_id}:{int(time.time())}")
        tx = self._send(
            self.reputation.functions.submitFeedback(
                agent_id, score, outcome_ref, comment[:200], 0
            ),
            gas=200_000,
        )
        print(f"[HACKATHON] Reputation submitted! score={score} tx={tx}")
        return tx

    # ── Read ──────────────────────────────────────────────────────────────────
    def get_stats(self, agent_id: int) -> dict:
        try:
            val_score  = self.validation.functions.getAverageValidationScore(agent_id).call()
            rep_score  = self.reputation.functions.getAverageScore(agent_id).call()
            trade_rec  = self.router.functions.getTradeRecord(agent_id).call()
            vault_bal  = self.vault.functions.getBalance(agent_id).call()
            return {
                "agent_id":        agent_id,
                "validation_score": val_score,
                "reputation_score": rep_score,
                "total_intents":   trade_rec[0],
                "vault_balance_eth": Web3.from_wei(vault_bal, "ether"),
            }
        except Exception as e:
            return {"error": str(e)}