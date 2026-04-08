"""
CORTEX — Base Agent
Abstract base class for all agents in the trading desk.
Each agent is an LLM with a specialized system prompt and tools.
"""

from abc import ABC, abstractmethod
from typing import Optional
import json
import os
import httpx

from models.trade import AgentRole, CortexEvent, EventType


class BaseAgent(ABC):
    """
    Base class for all CORTEX agents.
    Each agent wraps an LLM call with a specific system prompt and role.
    """

    def __init__(self, role: AgentRole, name: str, description: str):
        self.role = role
        self.name = name
        self.description = description
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.model = "claude-sonnet-4-20250514"
        self.status = "idle"  # idle | thinking | acting | error

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Each agent defines its own system prompt."""
        pass

    @abstractmethod
    async def process(self, context: dict) -> CortexEvent:
        """
        Main processing method. Receives context, returns a CortexEvent.
        Context contains market data, previous events, portfolio state, etc.
        """
        pass

    async def call_llm(self, system_prompt: str, user_message: str) -> str:
        """
        Call Claude API with the agent's system prompt.
        Returns the text response.
        """
        self.status = "thinking"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 1024,
                        "system": system_prompt,
                        "messages": [
                            {"role": "user", "content": user_message}
                        ],
                    },
                )
                response.raise_for_status()
                data = response.json()

                # Extract text from response
                text = ""
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        text += block.get("text", "")

                self.status = "idle"
                return text

        except Exception as e:
            self.status = "error"
            raise RuntimeError(f"[{self.name}] LLM call failed: {e}")

    def create_event(self, event_type: EventType, data: dict) -> CortexEvent:
        """Helper to create a properly formatted event."""
        return CortexEvent(
            event_type=event_type,
            agent=self.role,
            data=data,
        )

    def log(self, message: str):
        """Simple logging with agent name."""
        status_icons = {
            "idle": "[idle]",
            "thinking": "[thinking]",
            "acting": "[acting]",
            "error": "[error]",
        }
        icon = status_icons.get(self.status, "[idle]")
        print(f"{icon} [{self.name}] {message}")

    def __repr__(self):
        return f"<Agent:{self.name} role={self.role.value} status={self.status}>"
