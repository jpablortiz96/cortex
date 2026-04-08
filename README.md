# CORTEX — Autonomous Trading Desk Protocol

> **Multi-agent trading infrastructure with verifiable trust.**
> 5 AI agents. Kraken CLI execution. ERC-8004 on-chain proof. Every decision verified.

---

## The Problem

AI trading agents today are black boxes. There is no way to verify whether an agent followed its strategy, respected its risk limits, or behaved as expected. When autonomous agents handle real capital, *"trust me"* is not good enough.

## The Solution

CORTEX is a protocol where specialized AI agents form an autonomous trading desk with institutional-grade checks and balances. Every trade intent is signed with EIP-712. Every decision — proposals, approvals, vetoes, executions, compliance checks — generates an immutable validation artifact on Ethereum via ERC-8004.

**CORTEX doesn't ask you to trust the agents. It lets you verify them.**

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                  CORTEX DASHBOARD                     │
│          Real-time WebSocket · React · Terminal UI     │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│               ORCHESTRATOR (Python)                   │
│     Event Bus · Agent Lifecycle · EIP-712 Signing     │
├──────────┬──────────┬──────────┬──────────┬──────────┤
│ ◈ STRAT  │ ◆ RISK   │ ◇ EXEC  │ □ COMPLY │ ⬡ AUDIT  │
│ Signals  │ Gating   │ Orders  │ Limits   │ On-Chain  │
├──────────┴──────────┴──────────┴──────────┴──────────┤
│                    TOOL LAYER                         │
│  Kraken CLI · PRISM API · ERC-8004 Contracts          │
└──────────────────────────────────────────────────────┘
```

## Agents

| Agent | Role | Key Capability |
|-------|------|----------------|
| **◈ Strategist** | Market analysis and trade proposals | Fuses Kraken CLI market data with PRISM AI signals (momentum, mean-reversion, volatility) |
| **◆ Risk Officer** | Trade gating — approves or **VETOES** | Enforces hard limits: max position size, exposure caps, drawdown thresholds, confidence minimums |
| **◇ Executor** | Order execution via Kraken CLI | Paper trading with real market prices, slippage simulation, fee calculation |
| **□ Compliance** | Portfolio health monitoring | Circuit breakers, exposure alerts, daily loss limits |
| **⬡ Auditor** | On-chain verification | Records every action to Ethereum Sepolia via ERC-8004 ValidationRegistry |

---

## On-Chain Infrastructure (Ethereum Sepolia)

| Contract | Address | Verified Source |
|----------|---------|-----------------|
| **CortexAgentRegistry** | [`0x108571d9bC12197a8c8E78C4A6eC30C424643FB0`](https://sepolia.etherscan.io/address/0x108571d9bC12197a8c8E78C4A6eC30C424643FB0#code) | [View on Etherscan](https://sepolia.etherscan.io/address/0x108571d9bC12197a8c8E78C4A6eC30C424643FB0#code) |
| **CortexValidationRegistry** | [`0x4f2529D5D38836189408726B18bDFeDe87BeBDD9`](https://sepolia.etherscan.io/address/0x4f2529D5D38836189408726B18bDFeDe87BeBDD9#code) | [View on Etherscan](https://sepolia.etherscan.io/address/0x4f2529D5D38836189408726B18bDFeDe87BeBDD9#code) |

- 5 agents registered as ERC-721 identity tokens (IDs #1–#5)
- Every trade generates EIP-712 signed intents and attestations
- Validation artifacts include: proposals, approvals, vetoes, executions, compliance checks
- Agent reputation scores computed on-chain from validation history

### Agent Metadata Endpoints

Each agent has a registration JSON following the ERC-8004 spec:

```
GET /api/agents/strategist/metadata
GET /api/agents/risk_officer/metadata
GET /api/agents/executor/metadata
GET /api/agents/compliance/metadata
GET /api/agents/auditor/metadata
```

> **Production note:** Metadata JSONs are served via API for the hackathon. In production, these would be uploaded to IPFS and the metadataURI in the AgentRegistry contract updated to point to the IPFS CIDs.

---

## Technology Stack

| Layer | Technology | Role |
|-------|-----------|------|
| **Execution** | Kraken CLI (Rust binary) | Market data retrieval and paper trade execution |
| **Intelligence** | PRISM API (Strykr) | AI-powered market signals, risk metrics, asset resolution |
| **Agents** | Claude API (Anthropic) | LLM-powered decision making with specialized system prompts |
| **Contracts** | Solidity 0.8.24 + Hardhat | ERC-8004 identity, validation, and reputation |
| **Signing** | EIP-712 | Typed data signatures for trade intents and attestations |
| **Backend** | Python + FastAPI + WebSockets | Orchestrator, agent coordination, real-time streaming |
| **Frontend** | React + WebSocket client | Real-time trading terminal dashboard |
| **Chain** | Ethereum Sepolia (testnet) | On-chain verification and agent identity |

---

## The Veto — Why CORTEX is Different

Most AI trading agents are single-agent systems: one bot, one strategy, no oversight. CORTEX introduces **adversarial cooperation** — agents that check each other.

When the Risk Officer determines a trade exceeds risk parameters, it issues a **VETO**:

```
◈ [Strategist]    → Proposing SHORT BTC · $400 · Confidence: 75%
◆ [Risk Officer]  → 🚫 VETOED — Stop-loss distance exceeds maximum drawdown threshold
◇ [Executor]      → Execution skipped — proposal was vetoed
⬡ [Auditor]       → Veto recorded on-chain · tx: 0xa3f8...
```

The veto is signed with EIP-712, recorded as a validation artifact on Ethereum, and permanently verifiable by anyone. **This is what trustless looks like.**

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Kraken CLI (`cargo install kraken-cli`)
- Anthropic API key

### Setup

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/cortex.git
cd cortex

# Install Python dependencies
cd backend
pip install -r requirements.txt

# Set environment variables
export ANTHROPIC_API_KEY="your-key"
export DEPLOYER_PRIVATE_KEY="your-wallet-private-key"
export PRISM_API_KEY="your-prism-key"  # optional

# Run the trading desk
python api.py
```

Open `http://localhost:8000` — click **CYCLE** to run a trading cycle.

### Deploy Contracts (optional — already deployed)

```bash
cd contracts
npm install
npx hardhat run scripts/deploy.js --network sepolia
```

---

## Trade Flow

```
1. Market data fetched via Kraken CLI + PRISM API signals
2. Strategist analyzes and proposes a trade (EIP-712 signed intent)
3. Risk Officer evaluates against hard limits → APPROVE or VETO (EIP-712 signed attestation)
4. If approved: Executor places order via Kraken CLI paper trading
5. Compliance Monitor checks portfolio health post-trade
6. Auditor records all validation artifacts on Ethereum Sepolia
7. Dashboard updates in real-time via WebSocket
```

---

## EIP-712 Signature Scheme

CORTEX implements typed data signatures for two key actions:

**TradeIntent** (signed by Strategist):
```
{asset, side, size, price, stopLoss, takeProfit, confidence, timestamp, agentId}
```

**RiskAttestation** (signed by Risk Officer):
```
{tradeId, decision, riskScore, reasoning, timestamp, agentId}
```

Domain:
```
{name: "CORTEX Trading Desk", version: "1", chainId: 11155111, verifyingContract: <ValidationRegistry>}
```

---

## Prizes Targeted

| Prize | How CORTEX Qualifies |
|-------|---------------------|
| **Best Trustless Trading Agent ($10K)** | Multi-agent protocol with ERC-8004 identity, EIP-712 signatures, on-chain validation artifacts, agent reputation |
| **Best Risk-Adjusted Return ($5K)** | Risk Officer with hard limits, position sizing, drawdown control, The Veto mechanism |
| **Best Validation & Trust Model ($2.5K)** | Every action generates verifiable validation artifacts on Ethereum, verified source on Etherscan |
| **Best Compliance & Risk Guardrails ($2.5K)** | Compliance agent with circuit breakers, exposure limits, daily loss caps |

---

## Repository Structure

```
cortex/
├── backend/
│   ├── agents/           # 5 specialized AI agents
│   ├── tools/            # Kraken CLI, PRISM API, Web3, EIP-712
│   ├── models/           # Data models and event types
│   ├── metadata/         # ERC-8004 Agent Registration JSONs
│   ├── orchestrator.py   # Trading desk coordinator
│   ├── api.py            # FastAPI + WebSocket server
│   └── main.py           # CLI runner
├── contracts/
│   ├── contracts/        # Solidity: AgentRegistry, ValidationRegistry
│   └── scripts/          # Deployment scripts
├── dashboard/
│   └── index.html        # Real-time trading terminal UI
└── README.md
```

---

## License

MIT

---

**Built for the [AI Trading Agents Hackathon](https://lablab.ai/ai-hackathons/ai-trading-agents) by lablab.ai · March 30 – April 12, 2026**

*CORTEX: Trust is proven, not promised.*