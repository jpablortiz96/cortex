"""
CORTEX - Executor Agent
Executes approved trades via Kraken CLI paper trading.
"""

import asyncio
import json
import random
import subprocess
from models.trade import (
    AgentRole, CortexEvent, EventType,
    TradeExecution
)
from agents.base import BaseAgent

KRAKEN_CLI_PAIRS = {
    "BTC": "XBTUSD",
    "ETH": "ETHUSD",
    "SOL": "SOLUSD",
}

VOLUME_PRECISION = {"BTC": 5, "ETH": 4, "SOL": 2}


class ExecutorAgent(BaseAgent):

    def __init__(self):
        super().__init__(
            role=AgentRole.EXECUTOR,
            name="Executor",
            description="Executes approved trades via Kraken CLI paper trading.",
        )
        self.paper_trading = True

    def get_system_prompt(self) -> str:
        return ""

    async def process(self, context: dict) -> CortexEvent:
        proposal = context.get("proposal", {})
        assessment = context.get("assessment", {})

        if assessment.get("decision") != "APPROVED":
            self.log(f"Skipping execution - proposal {proposal.get('id')} was VETOED")
            return self.create_event(
                EventType.EXECUTION,
                TradeExecution(proposal_id=proposal.get("id", ""), success=False).to_dict(),
            )

        self.log(f"Executing: {proposal.get('side')} {proposal.get('asset')} | ${proposal.get('size_usd')}")
        self.status = "acting"
        execution = await self._execute_kraken(proposal)
        self.status = "idle"

        if execution.success:
            self.log(f"Executed @ ${execution.executed_price:.2f} | Slippage: {execution.slippage_bps:.1f}bps | Fee: ${execution.fees:.2f}")
        else:
            self.log(f"Execution failed for proposal {proposal.get('id')}")

        return self.create_event(EventType.EXECUTION, execution.to_dict())

    async def _execute_kraken(self, proposal: dict) -> TradeExecution:
        asset = proposal.get("asset", "")
        side = proposal.get("side", "LONG")
        size_usd = proposal.get("size_usd", 0)
        entry_price = proposal.get("entry_price", 1)

        pair = KRAKEN_CLI_PAIRS.get(asset)
        if not pair:
            self.log(f"Unknown asset {asset}, falling back to simulation")
            return self._simulate_execution(proposal)

        precision = VOLUME_PRECISION.get(asset, 4)
        volume = round(size_usd / entry_price, precision)
        if volume <= 0:
            return self._simulate_execution(proposal)

        action = "buy" if side == "LONG" else "sell"
        cmd = ["kraken", "paper", action, pair, str(volume), "--type", "market", "-o", "json"]
        self.log(f"kraken paper {action} {pair} {volume} --type market")

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=30),
            )

            if result.returncode != 0:
                self.log(f"CLI error (rc={result.returncode}): {result.stderr.strip()[:100]}")
                return self._simulate_execution(proposal)

            data = json.loads(result.stdout)
            executed_price = float(data.get("price", entry_price))
            executed_volume = float(data.get("volume", volume))
            fee = float(data.get("fee", 0))
            order_id = data.get("order_id", "PAPER-unknown")
            slippage_bps = abs(executed_price - entry_price) / entry_price * 10000 if entry_price > 0 else 0.0

            return TradeExecution(
                proposal_id=proposal.get("id", ""),
                success=True,
                executed_price=round(executed_price, 2),
                executed_size=round(executed_volume, 8),
                order_id=order_id,
                exchange="kraken-cli-paper",
                fees=round(fee, 4),
                slippage_bps=round(slippage_bps, 2),
            )

        except subprocess.TimeoutExpired:
            self.log("CLI timeout - falling back to simulation")
            return self._simulate_execution(proposal)
        except (json.JSONDecodeError, KeyError) as e:
            self.log(f"CLI parse error: {e} - falling back to simulation")
            return self._simulate_execution(proposal)
        except FileNotFoundError:
            self.log("kraken CLI not found - falling back to simulation")
            return self._simulate_execution(proposal)

    def _simulate_execution(self, proposal: dict) -> TradeExecution:
        entry_price = proposal.get("entry_price", 0)
        size_usd = proposal.get("size_usd", 0)
        slippage_bps = random.uniform(1, 5)
        slippage_factor = 1 + (slippage_bps / 10000)
        executed_price = entry_price * slippage_factor if proposal.get("side") == "LONG" else entry_price / slippage_factor
        executed_size = size_usd / executed_price if executed_price > 0 else 0
        fees = size_usd * random.uniform(0.001, 0.0026)
        return TradeExecution(
            proposal_id=proposal.get("id", ""),
            success=True,
            executed_price=round(executed_price, 2),
            executed_size=round(executed_size, 8),
            order_id=f"PAPER-{proposal.get('id', 'x')}",
            exchange="kraken-paper-sim",
            fees=round(fees, 4),
            slippage_bps=round(slippage_bps, 2),
        )
