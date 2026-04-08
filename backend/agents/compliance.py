"""
CORTEX — Compliance Agent
Monitors portfolio health post-trade.
Can trigger circuit breakers if limits are breached.
"""

import json
from models.trade import (
    AgentRole, CortexEvent, EventType,
    ComplianceCheck
)
from agents.base import BaseAgent


class ComplianceAgent(BaseAgent):

    def __init__(self):
        super().__init__(
            role=AgentRole.COMPLIANCE,
            name="Compliance Monitor",
            description="Monitors portfolio health and enforces guardrails. Can trigger circuit breakers.",
        )
        # Hard limits
        self.max_daily_loss_pct = 5.0
        self.max_total_exposure_pct = 30.0
        self.max_open_positions = 5
        self.max_single_position_pct = 15.0

    def get_system_prompt(self) -> str:
        return f"""You are the COMPLIANCE MONITOR agent in the CORTEX Autonomous Trading Desk.

Your role: Monitor portfolio health AFTER trades are executed.
You are the last line of defense. You enforce hard limits.

HARD LIMITS (NON-NEGOTIABLE):
- Max daily loss: {self.max_daily_loss_pct}%
- Max total exposure: {self.max_total_exposure_pct}%
- Max open positions: {self.max_open_positions}
- Max single position: {self.max_single_position_pct}% of portfolio

YOUR JOB:
1. Check if any limits are breached
2. Generate alerts for near-breaches (within 80% of limit)
3. Trigger CIRCUIT BREAKER if hard limits are breached
4. Provide a clear status report

RESPOND ONLY WITH VALID JSON (no markdown, no backticks):
{{
    "all_clear": true | false,
    "total_exposure_pct": <number>,
    "daily_pnl_pct": <number>,
    "open_positions": <number>,
    "alerts": ["<alert message 1>", ...],
    "circuit_breaker_triggered": true | false
}}"""

    async def process(self, context: dict) -> CortexEvent:
        """
        Check portfolio compliance after a trade.
        """
        portfolio = context.get("portfolio_state", {})
        execution = context.get("execution", {})

        self.log("Running compliance check...")
        self.status = "thinking"

        user_message = f"""PORTFOLIO STATE AFTER LATEST TRADE:
{json.dumps(portfolio, indent=2)}

LATEST EXECUTION:
{json.dumps(execution, indent=2)}

Check all compliance limits and report status."""

        response_text = await self.call_llm(
            self.get_system_prompt(),
            user_message,
        )

        try:
            cleaned = response_text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            cleaned = cleaned.strip()

            data = json.loads(cleaned)
            check = ComplianceCheck(
                proposal_id=execution.get("proposal_id", ""),
                all_clear=bool(data["all_clear"]),
                total_exposure_pct=float(data["total_exposure_pct"]),
                daily_pnl_pct=float(data["daily_pnl_pct"]),
                open_positions=int(data["open_positions"]),
                alerts=data.get("alerts", []),
                circuit_breaker_triggered=bool(data["circuit_breaker_triggered"]),
            )

            self.status = "idle"

            if check.circuit_breaker_triggered:
                self.log("CIRCUIT BREAKER TRIGGERED - ALL TRADING HALTED")
            elif not check.all_clear:
                self.log(f"[WARN] Alerts: {', '.join(check.alerts)}")
            else:
                self.log(f"All clear - Exposure: {check.total_exposure_pct:.1f}% | PnL: {check.daily_pnl_pct:+.2f}%")

            return self.create_event(
                EventType.COMPLIANCE_CHECK,
                check.to_dict(),
            )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.status = "error"
            self.log(f"Compliance check parse failed: {e}")
            return self.create_event(
                EventType.COMPLIANCE_CHECK,
                ComplianceCheck(
                    all_clear=False,
                    alerts=[f"Compliance check failed: {e}"],
                ).to_dict(),
            )
