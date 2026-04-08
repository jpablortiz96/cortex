"""
CORTEX — Strategist Agent
Analyzes market data and generates trade proposals.
This is the "idea generator" of the trading desk.
"""

import json
from models.trade import (
    AgentRole, CortexEvent, EventType,
    TradeProposal, Side
)
from agents.base import BaseAgent


class StrategistAgent(BaseAgent):

    def __init__(self):
        super().__init__(
            role=AgentRole.STRATEGIST,
            name="Strategist",
            description="Analyzes market data and proposes trades based on momentum and mean-reversion signals.",
        )

    def get_system_prompt(self) -> str:
        return """You are the STRATEGIST agent in the CORTEX Autonomous Trading Desk.

Your role: Analyze market data and propose ONE specific trade.

You are a disciplined, institutional-grade trading strategist. You combine:
- Momentum signals (price trends, volume changes)
- Mean-reversion signals (RSI extremes, deviation from moving averages)
- Market structure (support/resistance levels, volatility)

MARKET INTELLIGENCE SOURCES:
You receive data from two sources:
1. Kraken CLI — real-time prices, RSI, volume, VWAP (primary)
2. PRISM API (Strykr) — AI-powered signals, technical indicators, risk metrics (supplemental)

When PRISM signals are present in the market data (fields: prism_signal, prism_strength, prism_net_score, prism_sharpe, prism_max_drawdown), incorporate them:
- A PRISM "bullish" + moderate/strong signal is confirmation for a LONG
- A PRISM "bearish" + moderate/strong signal is confirmation for a SHORT
- Mismatches between PRISM and your own analysis should LOWER your confidence
- Always mention PRISM signals in your rationale when they are present

RULES:
- Propose exactly ONE trade per analysis cycle.
- Be specific: asset, side (LONG/SHORT), size in USD, entry price, stop-loss, take-profit.
- Provide clear rationale for your trade.
- Your confidence score should honestly reflect signal strength (0.0 to 1.0).
- Maximum position size: $500 USD per trade.
- Only trade these assets: BTC, ETH, SOL.
- Sometimes, the best trade is NO trade. If signals are weak, set confidence below 0.3.

RESPOND ONLY WITH VALID JSON (no markdown, no backticks):
{
    "asset": "BTC" | "ETH" | "SOL",
    "side": "LONG" | "SHORT",
    "size_usd": <number>,
    "entry_price": <number>,
    "stop_loss": <number>,
    "take_profit": <number>,
    "rationale": "<clear reasoning>",
    "confidence": <0.0 to 1.0>,
    "signals": {
        "momentum": "<description>",
        "mean_reversion": "<description>",
        "volatility": "<description>",
        "prism": "<what PRISM signals say, or N/A if not available>"
    }
}"""

    async def process(self, context: dict) -> CortexEvent:
        """
        Analyze market data and generate a trade proposal.
        Context should contain: market_data, portfolio_state, recent_trades
        """
        self.log("Analyzing market conditions...")
        self.status = "thinking"

        # Build the user message with market context
        market_data = context.get("market_data", {})
        portfolio = context.get("portfolio_state", {})
        recent_events = context.get("recent_events", [])

        user_message = f"""Current Market Data:
{json.dumps(market_data, indent=2)}

Current Portfolio State:
{json.dumps(portfolio, indent=2)}

Recent Activity:
{json.dumps(recent_events[-5:] if recent_events else [], indent=2)}

Analyze the market and propose a trade. Remember: if signals are weak, reflect that in low confidence."""

        # Call LLM
        response_text = await self.call_llm(
            self.get_system_prompt(),
            user_message,
        )

        # Parse response into TradeProposal
        try:
            # Clean response - remove markdown backticks if present
            cleaned = response_text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            cleaned = cleaned.strip()

            data = json.loads(cleaned)
            proposal = TradeProposal(
                asset=data["asset"],
                side=Side(data["side"]),
                size_usd=float(data["size_usd"]),
                entry_price=float(data["entry_price"]),
                stop_loss=float(data["stop_loss"]),
                take_profit=float(data["take_profit"]),
                rationale=data["rationale"],
                confidence=float(data["confidence"]),
                signals=data.get("signals", {}),
            )

            self.status = "idle"
            self.log(f"Proposed: {proposal.side.value} {proposal.asset} | ${proposal.size_usd} | Confidence: {proposal.confidence:.0%}")

            return self.create_event(
                EventType.PROPOSAL,
                proposal.to_dict(),
            )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.status = "error"
            self.log(f"Failed to parse proposal: {e}")
            # Return a low-confidence skip event
            return self.create_event(
                EventType.PROPOSAL,
                TradeProposal(
                    asset="NONE",
                    rationale=f"Failed to generate valid proposal: {e}",
                    confidence=0.0,
                ).to_dict(),
            )
