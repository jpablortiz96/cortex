"""
CORTEX — Hackathon Setup Script
Run ONCE: python backend/scripts/hackathon_setup.py

Steps:
  1. Register CORTEX in the official AgentRegistry
  2. Claim 0.05 ETH from HackathonVault
  3. Set risk params in RiskRouter
  4. Save agent_id to hackathon_agent.json
"""

import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from tools.hackathon_client import HackathonClient

SAVE_PATH = os.path.join(os.path.dirname(__file__), "..", "hackathon_agent.json")


def main():
    client = HackathonClient()

    # Check if already registered
    if os.path.exists(SAVE_PATH):
        with open(SAVE_PATH) as f:
            existing = json.load(f)
        print(f"[INFO] Already registered! agent_id={existing['agent_id']}")
        print(f"[INFO] Delete {SAVE_PATH} to re-register.")
        agent_id = existing["agent_id"]
    else:
        # STEP 1: Register
        result = client.register_agent()
        agent_id = result["agent_id"]
        data = {
            "agent_id":             agent_id,
            "register_tx":          result["tx_hash"],
            "agent_registry":       "0x97b07dDc405B0c28B17559aFFE63BdB3632d0ca3",
            "hackathon_vault":      "0x0E7CD8ef9743FEcf94f9103033a044caBD45fC90",
            "risk_router":          "0xd6A6952545FF6E6E6681c2d15C59f9EB8F40FdBC",
            "validation_registry":  "0x92bF63E5C7Ac6980f237a7164Ab413BE226187F1",
            "reputation_registry":  "0x423a9904e39537a9997fbaF0f220d79D7d545763",
            "network":              "sepolia",
            "explorer":             f"https://sepolia.etherscan.io/tx/{result['tx_hash']}",
        }
        with open(SAVE_PATH, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\n[SUCCESS] agent_id={agent_id} saved to {SAVE_PATH}")

    # STEP 2: Claim allocation
    print("\n--- Claiming vault allocation ---")
    try:
        client.claim_allocation(agent_id)
    except Exception as e:
        print(f"[WARN] Vault claim failed (may already be claimed or vault empty): {e}")

    # STEP 3: Set risk params
    print("\n--- Setting risk params in RiskRouter ---")
    try:
        client.set_risk_params(agent_id)
    except Exception as e:
        print(f"[WARN] setRiskParams failed: {e}")

    # Stats
    print("\n--- Current stats ---")
    stats = client.get_stats(agent_id)
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print(f"\n[DONE] Setup complete. agent_id={agent_id}")
    print(f"[DONE] Now run: python backend/scripts/hackathon_blast.py")


if __name__ == "__main__":
    main()