"""
ERC-8004 Hackathon Registry Client
Registers CORTEX on the official ERC-8004 IdentityRegistry + ValidationRegistry on Sepolia.
"""

import asyncio
import os
from web3 import Web3
from eth_account import Account

# Sepolia contract addresses (deterministic CREATE2 deployment)
IDENTITY_REGISTRY   = "0x8004A818BFB912233c491871b3d84c89A494BD9e"
REPUTATION_REGISTRY = "0x8004B663056A597Dffe9eCcC1965A193B7388713"

# Minimal ABIs — only the functions we need
IDENTITY_ABI = [
    {
        "inputs": [{"internalType": "string", "name": "agentURI", "type": "string"}],
        "name": "register",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "ownerOf",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True,  "name": "from",    "type": "address"},
            {"indexed": True,  "name": "to",      "type": "address"},
            {"indexed": True,  "name": "tokenId", "type": "uint256"}
        ],
        "name": "Transfer",
        "type": "event"
    }
]

REPUTATION_ABI = [
    {
        "inputs": [
            {"internalType": "uint256",  "name": "agentId",        "type": "uint256"},
            {"internalType": "int128",   "name": "value",           "type": "int128"},
            {"internalType": "uint8",    "name": "valueDecimals",   "type": "uint8"},
            {"internalType": "string",   "name": "tag1",            "type": "string"},
            {"internalType": "string",   "name": "tag2",            "type": "string"},
            {"internalType": "string",   "name": "endpoint",        "type": "string"},
            {"internalType": "string",   "name": "feedbackURI",     "type": "string"},
            {"internalType": "bytes32",  "name": "feedbackHash",    "type": "bytes32"}
        ],
        "name": "giveFeedback",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256",   "name": "agentId",          "type": "uint256"},
            {"internalType": "address[]", "name": "clientAddresses",  "type": "address[]"},
            {"internalType": "string",    "name": "tag1",             "type": "string"},
            {"internalType": "string",    "name": "tag2",             "type": "string"}
        ],
        "name": "getSummary",
        "outputs": [
            {"internalType": "uint64",  "name": "count",        "type": "uint64"},
            {"internalType": "int128",  "name": "summaryValue", "type": "int128"},
            {"internalType": "uint8",   "name": "summaryValueDecimals", "type": "uint8"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]


class ERC8004Client:
    def __init__(self):
        rpc = os.getenv("SEPOLIA_RPC", "https://ethereum-sepolia-rpc.publicnode.com")
        self.w3 = Web3(Web3.HTTPProvider(rpc))
        pk = os.getenv("DEPLOYER_PRIVATE_KEY", "")
        self.account = Account.from_key(pk) if pk else None
        self.identity  = self.w3.eth.contract(
            address=Web3.to_checksum_address(IDENTITY_REGISTRY), abi=IDENTITY_ABI)
        self.reputation = self.w3.eth.contract(
            address=Web3.to_checksum_address(REPUTATION_REGISTRY), abi=REPUTATION_ABI)

    def _send(self, fn):
        """Build, sign and send a transaction. Returns tx_hash."""
        if not self.account:
            raise RuntimeError("DEPLOYER_PRIVATE_KEY not set")
        nonce = self.w3.eth.get_transaction_count(self.account.address, "pending")
        block = self.w3.eth.get_block("latest")
        base_fee = block.get("baseFeePerGas", Web3.to_wei(10, "gwei"))
        max_fee  = base_fee * 3 + Web3.to_wei(1, "gwei")
        tx = fn.build_transaction({
            "from":                 self.account.address,
            "nonce":                nonce,
            "gas":                  300_000,
            "maxFeePerGas":         max_fee,
            "maxPriorityFeePerGas": Web3.to_wei(1, "gwei"),
            "chainId":              11155111,
        })
        signed = self.w3.eth.account.sign_transaction(tx, self.account.key)
        return self.w3.eth.send_raw_transaction(signed.raw_transaction)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def register_agent(self, agent_uri: str) -> dict:
        """Mint an ERC-8004 identity NFT. Returns {agent_id, tx_hash}."""
        tx_hash = self._send(self.identity.functions.register(agent_uri))
        print(f"[ERC-8004] Registration tx sent: {tx_hash.hex()}")
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt.status != 1:
            raise RuntimeError("Registration tx reverted")

        # Extract tokenId from Transfer event (from=0x0 means mint)
        transfer_topic = self.w3.keccak(text="Transfer(address,address,uint256)")
        agent_id = None
        for log in receipt.logs:
            if log.topics and log.topics[0] == transfer_topic:
                agent_id = int(log.topics[3].hex(), 16)
                break

        print(f"[ERC-8004] Agent registered! ID={agent_id}")
        return {"agent_id": agent_id, "tx_hash": tx_hash.hex()}

    # ------------------------------------------------------------------
    # Reputation signals
    # ------------------------------------------------------------------
    def record_trade_signal(self, agent_id: int, score: int, tag1: str, tag2: str,
                             endpoint: str, feedback_uri: str = "", feedback_hash: bytes = b"\x00" * 32) -> str:
        """
        Submit a reputation signal for a completed trade.
        score: 0-100 integer
        tag1: e.g. "trade" or "risk"
        tag2: e.g. "BTC" or "ETH"
        """
        if isinstance(feedback_hash, str):
            feedback_hash = bytes.fromhex(feedback_hash.replace("0x","").ljust(64,"0"))
        tx_hash = self._send(
            self.reputation.functions.giveFeedback(
                agent_id,
                score,   # value (int128) — 0-100 with 0 decimals
                0,       # valueDecimals
                tag1,
                tag2,
                endpoint,
                feedback_uri,
                feedback_hash
            )
        )
        print(f"[ERC-8004] Reputation signal tx: {tx_hash.hex()}")
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt.status != 1:
            raise RuntimeError("giveFeedback tx reverted")
        print(f"[ERC-8004] Signal recorded! score={score} tag={tag1}/{tag2}")
        return tx_hash.hex()

    def get_reputation_summary(self, agent_id: int, tag1: str = "", tag2: str = "") -> dict:
        """Read current reputation score from chain."""
        count, value, decimals = self.reputation.functions.getSummary(
            agent_id, [], tag1, tag2
        ).call()
        return {"count": count, "score": value, "decimals": decimals}