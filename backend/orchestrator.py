"""
CORTEX — Orchestrator
The brain of the trading desk. Coordinates the flow between agents.
Manages state, event bus, and agent lifecycle.
"""

import asyncio
import json
from datetime import datetime
from typing import Optional

from agents.strategist import StrategistAgent
from agents.risk_officer import RiskOfficerAgent
from agents.executor import ExecutorAgent
from agents.compliance import ComplianceAgent
from agents.auditor import AuditorAgent
from models.trade import CortexEvent, EventType, Decision, AgentRole
from tools.market_data import get_full_market_data
from tools.web3_client import CortexWeb3Client
from tools.eip712_signer import EIP712Signer
from tools.erc8004_client import ERC8004Client


class PortfolioState:
    """Tracks portfolio status across trading cycles."""

    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: list[dict] = []
        self.trade_history: list[dict] = []
        self.daily_pnl: float = 0.0
        self.total_pnl: float = 0.0
        self.circuit_breaker_active: bool = False

    def to_dict(self) -> dict:
        total_exposure = sum(p.get("size_usd", 0) for p in self.positions)
        exposure_pct = (total_exposure / self.initial_capital * 100) if self.initial_capital > 0 else 0
        return {
            "initial_capital": self.initial_capital,
            "cash": round(self.cash, 2),
            "total_value": round(self.cash + total_exposure, 2),
            "positions": self.positions,
            "open_positions_count": len(self.positions),
            "total_exposure_usd": round(total_exposure, 2),
            "total_exposure_pct": round(exposure_pct, 2),
            "daily_pnl": round(self.daily_pnl, 2),
            "daily_pnl_pct": round(self.daily_pnl / self.initial_capital * 100, 4) if self.initial_capital > 0 else 0,
            "total_pnl": round(self.total_pnl, 2),
            "total_trades": len(self.trade_history),
            "circuit_breaker_active": self.circuit_breaker_active,
        }

    def add_position(self, proposal: dict, execution: dict):
        """Record a new position from an executed trade."""
        if execution.get("success"):
            position = {
                "id": proposal.get("id"),
                "asset": proposal.get("asset"),
                "side": proposal.get("side"),
                "size_usd": execution.get("executed_size", 0) * execution.get("executed_price", 0),
                "entry_price": execution.get("executed_price"),
                "quantity": execution.get("executed_size"),
                "opened_at": execution.get("timestamp"),
            }
            self.positions.append(position)
            self.cash -= position["size_usd"] + execution.get("fees", 0)
            self.trade_history.append({
                "proposal": proposal,
                "execution": execution,
                "timestamp": execution.get("timestamp"),
            })


class Orchestrator:
    """
    Main orchestrator that runs the trading desk cycle.
    Flow: Strategist → Risk Officer → Executor → Compliance
    """

    def __init__(self, initial_capital: float = 10000.0):
        # Initialize Web3 client (connects to smart contracts)
        self.web3_client = CortexWeb3Client()
        self.eip712 = EIP712Signer()

        # ERC-8004 hackathon registry client
        import json as _json, os as _os
        self.erc8004 = ERC8004Client()
        _reg_path = _os.path.join(_os.path.dirname(__file__), 'erc8004_registration.json')
        self._erc8004_agent_id = None
        if _os.path.exists(_reg_path):
            with open(_reg_path) as _f:
                _reg = _json.load(_f)
            self._erc8004_agent_id = _reg.get('agent_id')
            print(f'[ERC-8004] Loaded agent_id={self._erc8004_agent_id} from registration')

        # Initialize agents
        self.strategist = StrategistAgent()
        self.risk_officer = RiskOfficerAgent()
        self.executor = ExecutorAgent()
        self.compliance = ComplianceAgent()
        self.auditor = AuditorAgent(self.web3_client)

        # State
        self.portfolio = PortfolioState(initial_capital)
        self.event_log: list[dict] = []
        self.cycle_count: int = 0
        self.running: bool = False

        # Callbacks for dashboard (WebSocket updates)
        self.on_event = None  # async callback(event_dict)

    async def emit_event(self, event: CortexEvent):
        """Log event and notify listeners."""
        event_dict = event.to_dict()
        self.event_log.append(event_dict)
        if self.on_event:
            await self.on_event(event_dict)

    async def get_market_data(self) -> dict:
        """
        Get current market data from Kraken public API.
        Falls back to simulated data if API fails.
        """
        try:
            data = await get_full_market_data(["BTC", "ETH", "SOL"])
            if data.get("assets"):
                return data
        except Exception as e:
            print(f"[WARN] Real market data failed, using fallback: {e}")

        # Fallback to simulated data
        import random
        btc_price = 84000 + random.uniform(-2000, 2000)
        eth_price = 1800 + random.uniform(-100, 100)
        sol_price = 135 + random.uniform(-15, 15)

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "source": "simulated_fallback",
            "assets": {
                "BTC": {
                    "price": round(btc_price, 2),
                    "change_24h_pct": round(random.uniform(-5, 5), 2),
                    "volume_24h": round(random.uniform(20e9, 40e9), 0),
                    "rsi_14": round(random.uniform(25, 75), 1),
                    "volatility_24h": round(random.uniform(1, 5), 2),
                },
                "ETH": {
                    "price": round(eth_price, 2),
                    "change_24h_pct": round(random.uniform(-7, 7), 2),
                    "volume_24h": round(random.uniform(10e9, 20e9), 0),
                    "rsi_14": round(random.uniform(25, 75), 1),
                    "volatility_24h": round(random.uniform(2, 7), 2),
                },
                "SOL": {
                    "price": round(sol_price, 2),
                    "change_24h_pct": round(random.uniform(-10, 10), 2),
                    "volume_24h": round(random.uniform(2e9, 8e9), 0),
                    "rsi_14": round(random.uniform(20, 80), 1),
                    "volatility_24h": round(random.uniform(3, 10), 2),
                },
            },
        }

    async def run_cycle(self) -> dict:
        """
        Run one complete trading desk cycle.
        This is the core loop: Strategist → Risk → Executor → Compliance
        """
        self.cycle_count += 1
        cycle_result = {"cycle": self.cycle_count, "events": []}

        print(f"\n{'='*60}")
        print(f"  CORTEX — Trading Cycle #{self.cycle_count}")
        print(f"  {datetime.utcnow().isoformat()}")
        print(f"{'='*60}\n")

        # Check circuit breaker
        if self.portfolio.circuit_breaker_active:
            print("[CIRCUIT BREAKER] CIRCUIT BREAKER ACTIVE — Skipping cycle")
            return cycle_result

        # 1. Get market data
        market_data = await self.get_market_data()
        source = market_data.get("source", "unknown")
        source_label = "LIVE" if source in ("kraken_public_api", "kraken-cli") else "SIMULATED"
        print(f"[MARKET] Market [{source_label}]: BTC ${market_data['assets']['BTC']['price']:,.2f} | ETH ${market_data['assets']['ETH']['price']:,.2f} | SOL ${market_data['assets']['SOL']['price']:,.2f}")
        
        # Show RSI + PRISM signals if available
        for asset in ["BTC", "ETH", "SOL"]:
            a = market_data["assets"].get(asset, {})
            rsi = a.get("rsi_14", "N/A")
            chg = a.get("change_24h_pct", 0)
            vol = a.get("volatility_24h", 0)
            prism = a.get("prism_signal", "")
            prism_str = a.get("prism_strength", "")
            prism_label = f" | PRISM: {prism.upper()} ({prism_str})" if prism else ""
            print(f"   {asset}: RSI={rsi} | 24h={chg:+.2f}% | Vol={vol:.2f}%{prism_label}")
        print()

        # 2. STRATEGIST — Analyze and propose
        print("-" * 40)
        strategist_context = {
            "market_data": market_data,
            "portfolio_state": self.portfolio.to_dict(),
            "recent_events": self.event_log[-10:],
        }
        proposal_event = await self.strategist.process(strategist_context)
        await self.emit_event(proposal_event)
        cycle_result["events"].append(proposal_event.to_dict())

        proposal_data = proposal_event.data

        # Sign trade intent with EIP-712
        if proposal_data.get("asset") not in (None, "NONE"):
            intent_sig = self.eip712.sign_trade_intent(proposal_data)
            if intent_sig:
                proposal_data["eip712_signature"] = intent_sig
                print(f"   [EIP-712] TradeIntent signed: {intent_sig['message_hash'][:20]}...")

        # Skip if confidence too low or no valid proposal
        if proposal_data.get("confidence", 0) < 0.3 or proposal_data.get("asset") == "NONE":
            print(f"\n[SKIP]  Strategist confidence too low ({proposal_data.get('confidence', 0):.0%}). Skipping cycle.\n")
            return cycle_result

        # 3. RISK OFFICER — Evaluate proposal
        print("-" * 40)
        risk_context = {
            "proposal": proposal_data,
            "portfolio_state": self.portfolio.to_dict(),
        }
        risk_event = await self.risk_officer.process(risk_context)
        await self.emit_event(risk_event)
        cycle_result["events"].append(risk_event.to_dict())

        assessment_data = risk_event.data

        # Sign risk attestation with EIP-712
        attestation_sig = self.eip712.sign_risk_attestation(assessment_data)
        if attestation_sig:
            assessment_data["eip712_signature"] = attestation_sig
            print(f"   [EIP-712] RiskAttestation signed: {attestation_sig['message_hash'][:20]}...")

        # 4. EXECUTOR — Execute if approved
        print("-" * 40)
        exec_context = {
            "proposal": proposal_data,
            "assessment": assessment_data,
        }
        exec_event = await self.executor.process(exec_context)
        await self.emit_event(exec_event)
        cycle_result["events"].append(exec_event.to_dict())

        execution_data = exec_event.data

        # Update portfolio if trade was executed
        if execution_data.get("success"):
            self.portfolio.add_position(proposal_data, execution_data)

        # 5. COMPLIANCE — Post-trade check
        print("-" * 40)
        compliance_context = {
            "portfolio_state": self.portfolio.to_dict(),
            "execution": execution_data,
        }
        compliance_event = await self.compliance.process(compliance_context)
        await self.emit_event(compliance_event)
        cycle_result["events"].append(compliance_event.to_dict())

        compliance_data = compliance_event.data
        if compliance_data.get("circuit_breaker_triggered"):
            self.portfolio.circuit_breaker_active = True

        # 6. AUDITOR — Record everything on-chain (ERC-8004)
        if self.web3_client.enabled:
            print("-" * 40)
            audit_results = await self.auditor.record_trade_lifecycle(
                cycle_number=self.cycle_count,
                events=[e for e in cycle_result["events"]],
            )
            cycle_result["on_chain"] = audit_results

            # Broadcast audit results to dashboard
            if audit_results:
                audit_event = CortexEvent(
                    event_type=EventType.AUDIT_LOG,
                    agent=AgentRole.AUDITOR if hasattr(self, '_audit_role') else self.auditor.role,
                    data={
                        "artifacts_recorded": len(audit_results),
                        "tx_hashes": [r["tx_hash"][:16] + "..." for r in audit_results],
                        "explorer_links": [r.get("explorer_link", "") for r in audit_results if r.get("explorer_link")],
                    },
                )
                await self.emit_event(audit_event)

        # ERC-8004 Hackathon: record reputation signal after every cycle
        if self._erc8004_agent_id:
            try:
                import asyncio as _aio
                loop = _aio.get_event_loop()
                decision = cycle_result.get('decision', 'HOLD')
                asset = cycle_result.get('asset', 'BTC')
                score = 80 if decision in ('BUY', 'SELL') else 60
                endpoint = 'https://web-production-df8ac.up.railway.app/api/agents/strategist/metadata'
                tag1 = 'trade'
                tag2 = asset.upper()[:10]
                await loop.run_in_executor(
                    None,
                    lambda: self.erc8004.record_trade_signal(
                        self._erc8004_agent_id, score, tag1, tag2, endpoint
                    )
                )
                print(f'[ERC-8004] Reputation signal sent: score={score} tag={tag1}/{tag2}')
            except Exception as _e:
                print(f'[ERC-8004] Signal failed (non-fatal): {_e}')

        # Summary
        print(f"\n{'-'*40}")
        ps = self.portfolio.to_dict()
        print(f"[PORTFOLIO] Portfolio: ${ps['total_value']:,.2f} | Exposure: {ps['total_exposure_pct']:.1f}% | Positions: {ps['open_positions_count']} | Trades: {ps['total_trades']}")
        if self.web3_client.enabled:
            print(f"[ON-CHAIN] On-chain: {self.auditor.artifacts_recorded} total artifacts recorded")
        print()

        return cycle_result

    async def run(self, num_cycles: int = 3, delay_seconds: int = 5):
        """Run multiple trading cycles."""
        self.running = True

        chain_status = "Base Sepolia (ERC-8004)" if self.web3_client.enabled else "Off-chain only"
        print(f"""
+----------------------------------------------+
|     CORTEX - Autonomous Trading Desk         |
|     Capital: ${self.portfolio.initial_capital:,.2f}                    |
|     Chain: {chain_status:<35}|
+----------------------------------------------+
        """)

        for i in range(num_cycles):
            if not self.running:
                break
            await self.run_cycle()
            if i < num_cycles - 1:
                print(f"[WAIT] Next cycle in {delay_seconds}s...\n")
                await asyncio.sleep(delay_seconds)

        self.running = False
        print(f"\n{'='*60}")
        print(f"  CORTEX — Session Complete")
        print(f"  Total cycles: {self.cycle_count}")
        ps = self.portfolio.to_dict()
        print(f"  Final value: ${ps['total_value']:,.2f}")
        print(f"  Total PnL: ${ps['total_pnl']:,.2f}")
        print(f"  Trades executed: {ps['total_trades']}")
        print(f"{'='*60}")

    def stop(self):
        """Stop the orchestrator."""
        self.running = False
