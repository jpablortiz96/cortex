"""
CORTEX — Risk Officer Agent
Evaluates trade proposals against risk parameters.
This is the "guardian" of the trading desk. THE VETO lives here.
"""

import json
from models.trade import (
    AgentRole, CortexEvent, EventType,
    RiskAssessment, Decision
)
from agents.base import BaseAgent


class RiskOfficerAgent(BaseAgent):

    def __init__(self):
        super().__init__(
            role=AgentRole.RISK_OFFICER,
            name="Risk Officer",
            description="Evaluates every trade proposal against risk parameters. Can VETO trades.",
        )
        # Risk parameters — these are the guardrails
        self.max_position_size_usd = 500
        self.max_portfolio_exposure_pct = 30  # max 30% of portfolio in active trades
        self.max_single_asset_exposure_pct = 15
        self.max_daily_drawdown_pct = 5
        self.min_confidence_threshold = 0.4
        self.max_risk_reward_ratio = 0.5  # stop_loss / take_profit distance

    def get_system_prompt(self) -> str:
        return f"""You are the RISK OFFICER agent in the CORTEX Autonomous Trading Desk.

Your role: Evaluate trade proposals and APPROVE or VETO them.

You are a strict, conservative risk manager. Your job is to PROTECT CAPITAL.
You would rather miss a profitable trade than approve a risky one.

RISK PARAMETERS (HARD LIMITS — NEVER OVERRIDE):
- Max position size: ${self.max_position_size_usd} USD
- Max portfolio exposure: {self.max_portfolio_exposure_pct}%
- Max single asset exposure: {self.max_single_asset_exposure_pct}%
- Max daily drawdown: {self.max_daily_drawdown_pct}%
- Min confidence to approve: {self.min_confidence_threshold}

YOUR ANALYSIS MUST INCLUDE:
1. Position size check: Is the size within limits?
2. Risk/reward ratio: Is stop-loss distance reasonable vs take-profit?
3. Portfolio exposure: Will this trade push total exposure too high?
4. Confidence check: Is the strategist's confidence above minimum?
5. Rationale quality: Does the reasoning make sense?

BE AGGRESSIVE IN VETOING:
- If confidence is low → VETO
- If risk/reward is poor → VETO
- If exposure is too high → VETO
- If rationale is vague → VETO
- If stop-loss is too wide → VETO

RESPOND ONLY WITH VALID JSON (no markdown, no backticks):
{{
    "decision": "APPROVED" | "VETOED",
    "reasoning": "<detailed explanation of your decision>",
    "risk_score": <0-10, where 10 is maximum risk>,
    "max_drawdown_pct": <estimated max drawdown %>,
    "position_size_ok": true | false,
    "correlation_ok": true | false,
    "exposure_after": <total portfolio exposure % after this trade>
}}"""

    async def process(self, context: dict) -> CortexEvent:
        """
        Evaluate a trade proposal.
        Context must contain: proposal (TradeProposal dict), portfolio_state
        """
        proposal = context.get("proposal", {})
        portfolio = context.get("portfolio_state", {})

        self.log(f"Evaluating proposal {proposal.get('id', '?')}: {proposal.get('side', '?')} {proposal.get('asset', '?')}")
        self.status = "thinking"

        user_message = f"""TRADE PROPOSAL TO EVALUATE:
{json.dumps(proposal, indent=2)}

CURRENT PORTFOLIO STATE:
{json.dumps(portfolio, indent=2)}

Evaluate this trade proposal against all risk parameters. Be thorough and strict."""

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
            assessment = RiskAssessment(
                proposal_id=proposal.get("id", ""),
                decision=Decision(data["decision"]),
                reasoning=data["reasoning"],
                risk_score=float(data["risk_score"]),
                max_drawdown_pct=float(data["max_drawdown_pct"]),
                position_size_ok=bool(data["position_size_ok"]),
                correlation_ok=bool(data["correlation_ok"]),
                exposure_after=float(data["exposure_after"]),
            )

            self.status = "idle"

            # Log with drama — this is the key moment
            if assessment.decision == Decision.VETOED:
                self.log(f"VETOED: {assessment.reasoning[:80]}...")
            else:
                self.log(f"APPROVED - Risk Score: {assessment.risk_score}/10")

            return self.create_event(
                EventType.RISK_ASSESSMENT,
                assessment.to_dict(),
            )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.status = "error"
            self.log(f"Failed to parse assessment: {e}")
            # Default to VETO on parse failure (conservative)
            return self.create_event(
                EventType.RISK_ASSESSMENT,
                RiskAssessment(
                    proposal_id=proposal.get("id", ""),
                    decision=Decision.VETOED,
                    reasoning=f"Risk assessment failed to process: {e}. Defaulting to VETO.",
                    risk_score=10.0,
                ).to_dict(),
            )
