"""
CORTEX — Web3 Client
Connects the Python backend to the ERC-8004 smart contracts on Base Sepolia.
Handles all on-chain interactions: recording validations, reading reputation, etc.
"""

import json
import os
import hashlib
from typing import Optional
from web3 import Web3
from eth_account import Account


# ABI fragments — only the functions we call (keeps it lightweight)
AGENT_REGISTRY_ABI = [
    {
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "name": "getAgent",
        "outputs": [{"components": [
            {"name": "role", "type": "string"},
            {"name": "name", "type": "string"},
            {"name": "agentWallet", "type": "address"},
            {"name": "metadataURI", "type": "string"},
            {"name": "registeredAt", "type": "uint256"},
            {"name": "active", "type": "bool"},
        ], "name": "", "type": "tuple"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "totalAgents",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

VALIDATION_REGISTRY_ABI = [
    {
        "inputs": [
            {"name": "agentTokenId", "type": "uint256"},
            {"name": "vType", "type": "uint8"},
            {"name": "tradeId", "type": "string"},
            {"name": "dataHash", "type": "string"},
            {"name": "summary", "type": "string"},
            {"name": "cycleNumber", "type": "uint256"},
        ],
        "name": "recordValidation",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "tradeId", "type": "string"}],
        "name": "getTradeValidations",
        "outputs": [{"name": "", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "artifactId", "type": "uint256"}],
        "name": "getArtifact",
        "outputs": [{"components": [
            {"name": "id", "type": "uint256"},
            {"name": "agentTokenId", "type": "uint256"},
            {"name": "vType", "type": "uint8"},
            {"name": "tradeId", "type": "string"},
            {"name": "dataHash", "type": "string"},
            {"name": "summary", "type": "string"},
            {"name": "timestamp", "type": "uint256"},
            {"name": "cycleNumber", "type": "uint256"},
        ], "name": "", "type": "tuple"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "agentTokenId", "type": "uint256"}],
        "name": "getReputation",
        "outputs": [{"components": [
            {"name": "totalActions", "type": "uint256"},
            {"name": "approvals", "type": "uint256"},
            {"name": "vetoes", "type": "uint256"},
            {"name": "successfulTrades", "type": "uint256"},
            {"name": "compliancePasses", "type": "uint256"},
            {"name": "complianceAlerts", "type": "uint256"},
            {"name": "reputationScore", "type": "int256"},
        ], "name": "", "type": "tuple"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "totalArtifacts",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# Validation types matching the Solidity enum
VALIDATION_TYPES = {
    "trade_proposal": 0,
    "risk_approved": 1,
    "risk_vetoed": 2,
    "trade_executed": 3,
    "compliance_clear": 4,
    "compliance_alert": 5,
    "circuit_breaker": 6,
}


class CortexWeb3Client:
    """
    Connects to the CORTEX smart contracts on Base Sepolia.
    """

    def __init__(self, deployment_path: str = None):
        self.enabled = False
        self.w3 = None
        self.account = None
        self.agent_registry = None
        self.validation_registry = None
        self.agent_token_ids = {}
        self.explorer_url = "https://sepolia.etherscan.io"
        self.tx_log = []  # Track all transactions for dashboard

        if deployment_path is None:
            deployment_path = os.path.join(
                os.path.dirname(__file__), "..", "deployment.json"
            )

        self._initialize(deployment_path)

    def _initialize(self, deployment_path: str):
        """Load deployment config and connect to contracts."""
        # Check if deployment exists
        if not os.path.exists(deployment_path):
            print("[WARN]  No deployment.json found — on-chain features disabled")
            print("    Deploy contracts first: cd contracts && npx hardhat run scripts/deploy.js --network sepolia")
            return

        # Check for private key
        private_key = os.getenv("DEPLOYER_PRIVATE_KEY")
        if not private_key:
            print("[WARN]  DEPLOYER_PRIVATE_KEY not set — on-chain features disabled")
            return

        try:
            with open(deployment_path) as f:
                deployment = json.load(f)

            rpc_url = os.getenv("SEPOLIA_RPC", "https://ethereum-sepolia-rpc.publicnode.com")
            self.w3 = Web3(Web3.HTTPProvider(rpc_url))

            if not self.w3.is_connected():
                print("[WARN]  Cannot connect to Sepolia — on-chain features disabled")
                return

            # Setup account
            if not private_key.startswith("0x"):
                private_key = "0x" + private_key
            self.account = Account.from_key(private_key)

            # Setup contracts
            contracts = deployment.get("contracts", {})
            self.agent_registry = self.w3.eth.contract(
                address=Web3.to_checksum_address(contracts["agentRegistry"]),
                abi=AGENT_REGISTRY_ABI,
            )
            self.validation_registry = self.w3.eth.contract(
                address=Web3.to_checksum_address(contracts["validationRegistry"]),
                abi=VALIDATION_REGISTRY_ABI,
            )

            self.agent_token_ids = deployment.get("agents", {})
            self.explorer_url = deployment.get("explorerBaseUrl", "")

            self.enabled = True
            total_agents = self.agent_registry.functions.totalAgents().call()
            print(f"[OK] On-chain connected: Sepolia | {total_agents} agents registered")
            print(f"   Agent Registry:      {contracts['agentRegistry']}")
            print(f"   Validation Registry: {contracts['validationRegistry']}")

        except Exception as e:
            print(f"[WARN]  Web3 initialization failed: {e}")
            self.enabled = False

    def _hash_data(self, data: dict) -> str:
        """
        Create a hash of event data for on-chain verification.
        If the data contains an EIP-712 signature, the message_hash from that
        signature is used directly — it is the canonical identifier for the intent.
        Otherwise falls back to SHA-256 of the full data payload.
        """
        sig = data.get("eip712_signature", {})
        if sig and sig.get("message_hash"):
            # Use the EIP-712 message hash as the canonical data hash.
            # Strip "0x" prefix so it fits cleanly as a hex string on-chain.
            return sig["message_hash"].lstrip("0x")
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()

    async def record_validation(
        self,
        agent_role: str,
        validation_type: str,
        trade_id: str,
        data: dict,
        summary: str,
        cycle_number: int,
    ) -> Optional[dict]:
        """
        Record a validation artifact on-chain.
        Returns tx hash and artifact ID, or None if disabled.
        """
        if not self.enabled:
            return None

        try:
            agent_token_id = int(self.agent_token_ids.get(agent_role, 0))
            v_type = VALIDATION_TYPES.get(validation_type, 0)
            data_hash = self._hash_data(data)

            # Truncate summary for gas efficiency
            summary_short = summary[:200] if len(summary) > 200 else summary

            # Build transaction — use pending nonce and dynamic gas price
            nonce = self.w3.eth.get_transaction_count(self.account.address, "pending")
            base_fee = self.w3.eth.get_block("latest")["baseFeePerGas"]
            max_fee = int(base_fee * 3)  # 3x base fee for reliable inclusion
            priority_fee = self.w3.to_wei("0.5", "gwei")

            tx = self.validation_registry.functions.recordValidation(
                agent_token_id,
                v_type,
                trade_id,
                data_hash,
                summary_short,
                cycle_number,
            ).build_transaction({
                "from": self.account.address,
                "nonce": nonce,
                "gas": 500000,
                "maxFeePerGas": max(max_fee, priority_fee + base_fee),
                "maxPriorityFeePerGas": priority_fee,
            })

            # Sign and send
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.account.key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            
            # Wait for confirmation
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)

            result = {
                "tx_hash": tx_hash.hex(),
                "block_number": receipt["blockNumber"],
                "gas_used": receipt["gasUsed"],
                "status": "confirmed" if receipt["status"] == 1 else "failed",
                "explorer_link": f"{self.explorer_url}/tx/0x{tx_hash.hex()}" if self.explorer_url else "",
                "agent_role": agent_role,
                "validation_type": validation_type,
                "trade_id": trade_id,
            }

            self.tx_log.append(result)
            return result

        except Exception as e:
            print(f"[WARN]  On-chain recording failed: {e}")
            return None

    def get_agent_reputation(self, agent_role: str) -> Optional[dict]:
        """Get an agent's on-chain reputation score."""
        if not self.enabled:
            return None

        try:
            token_id = int(self.agent_token_ids.get(agent_role, 0))
            if token_id == 0:
                return None

            rep = self.validation_registry.functions.getReputation(token_id).call()
            return {
                "total_actions": rep[0],
                "approvals": rep[1],
                "vetoes": rep[2],
                "successful_trades": rep[3],
                "compliance_passes": rep[4],
                "compliance_alerts": rep[5],
                "reputation_score": rep[6],
            }
        except Exception as e:
            print(f"[WARN]  Reputation read failed: {e}")
            return None

    def get_all_reputations(self) -> dict:
        """Get reputation for all agents."""
        reputations = {}
        for role in self.agent_token_ids:
            rep = self.get_agent_reputation(role)
            if rep:
                reputations[role] = rep
        return reputations

    def get_total_artifacts(self) -> int:
        """Get total validation artifacts recorded on-chain."""
        if not self.enabled:
            return 0
        try:
            return self.validation_registry.functions.totalArtifacts().call()
        except:
            return 0
