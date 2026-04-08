"""
CORTEX — Auditor Agent
Records every trading desk action on-chain via ERC-8004 contracts.
This is the trust layer — making the entire trading desk auditable and verifiable.

Unlike other agents, the Auditor doesn't use an LLM.
It's a deterministic recorder that maps events to on-chain validation artifacts.
"""

from models.trade import AgentRole, CortexEvent, EventType
from agents.base import BaseAgent
from tools.web3_client import CortexWeb3Client


class AuditorAgent(BaseAgent):

    def __init__(self, web3_client: CortexWeb3Client = None):
        super().__init__(
            role=AgentRole.AUDITOR,
            name="Auditor",
            description="Records all trading desk actions on-chain for verifiable trust.",
        )
        self.web3 = web3_client or CortexWeb3Client()
        self.artifacts_recorded = 0

    def get_system_prompt(self) -> str:
        return ""  # Auditor doesn't use LLM — it's deterministic

    async def process(self, context: dict) -> CortexEvent:
        """Not used — Auditor uses record_event instead."""
        pass

    async def record_trade_lifecycle(self, cycle_number: int, events: list[dict]) -> list[dict]:
        """
        Record an entire trade lifecycle on-chain.
        Takes the events from one orchestrator cycle and records each as a validation artifact.
        
        Returns list of on-chain transaction results.
        """
        if not self.web3.enabled:
            self.log("On-chain recording disabled — no deployment found")
            return []

        self.status = "acting"
        self.log(f"Recording cycle #{cycle_number} on-chain...")
        
        results = []

        for event in events:
            event_type = event.get("event_type", "")
            agent_role = event.get("agent", "")
            data = event.get("data", {})
            trade_id = data.get("id", data.get("proposal_id", "unknown"))

            # Map event types to validation types
            validation_type = None
            summary = ""

            if event_type == "trade_proposal":
                validation_type = "trade_proposal"
                sig = data.get("eip712_signature", {})
                sig_suffix = f" | EIP-712: {sig.get('message_hash', '')[:18]}..." if sig else ""
                summary = f"Proposed {data.get('side', '?')} {data.get('asset', '?')} ${data.get('size_usd', 0)} (confidence: {data.get('confidence', 0):.0%}){sig_suffix}"

            elif event_type == "risk_assessment":
                sig = data.get("eip712_signature", {})
                sig_suffix = f" | EIP-712: {sig.get('message_hash', '')[:18]}..." if sig else ""
                if data.get("decision") == "VETOED":
                    validation_type = "risk_vetoed"
                    summary = f"VETOED: {data.get('reasoning', 'No reason given')[:130]}{sig_suffix}"
                else:
                    validation_type = "risk_approved"
                    summary = f"APPROVED: Risk score {data.get('risk_score', '?')}/10{sig_suffix}"

            elif event_type == "trade_execution":
                if data.get("success"):
                    validation_type = "trade_executed"
                    summary = f"Executed @ ${data.get('executed_price', 0):,.2f} | Slippage: {data.get('slippage_bps', 0):.1f}bps"
                # Skip failed executions (vetoed trades)

            elif event_type == "compliance_check":
                if data.get("circuit_breaker_triggered"):
                    validation_type = "circuit_breaker"
                    summary = f"CIRCUIT BREAKER: {', '.join(data.get('alerts', []))}"
                elif not data.get("all_clear"):
                    validation_type = "compliance_alert"
                    summary = f"ALERT: {', '.join(data.get('alerts', []))}"
                else:
                    validation_type = "compliance_clear"
                    summary = f"All clear. Exposure: {data.get('total_exposure_pct', 0):.1f}%"

            if validation_type:
                result = await self.web3.record_validation(
                    agent_role=agent_role,
                    validation_type=validation_type,
                    trade_id=trade_id,
                    data=data,
                    summary=summary,
                    cycle_number=cycle_number,
                )

                if result:
                    self.artifacts_recorded += 1
                    status = "[OK]" if result["status"] == "confirmed" else "[FAIL]"
                    self.log(f"{status} Recorded: {validation_type} | tx: {result['tx_hash'][:16]}...")
                    results.append(result)

        self.status = "idle"
        self.log(f"Cycle #{cycle_number} recorded: {len(results)} artifacts on-chain (total: {self.artifacts_recorded})")
        
        return results

    def get_reputation_report(self) -> dict:
        """Get on-chain reputation for all agents."""
        return self.web3.get_all_reputations()

    def get_stats(self) -> dict:
        """Get auditor stats."""
        return {
            "artifacts_recorded": self.artifacts_recorded,
            "on_chain_enabled": self.web3.enabled,
            "total_on_chain": self.web3.get_total_artifacts(),
            "tx_log": self.web3.tx_log[-10:],  # Last 10 transactions
        }
