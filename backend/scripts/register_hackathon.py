"""
CORTEX — ERC-8004 Hackathon Registration Script
Run once: python backend/scripts/register_hackathon.py
"""

import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from tools.erc8004_client import ERC8004Client

# The agent metadata URI — points to our Railway backend
AGENT_URI = "https://web-production-df8ac.up.railway.app/api/agents/strategist/metadata"

REGISTRATION_FILE = os.path.join(os.path.dirname(__file__), "..", "erc8004_registration.json")


def main():
    client = ERC8004Client()

    # Check if already registered
    if os.path.exists(REGISTRATION_FILE):
        with open(REGISTRATION_FILE) as f:
            existing = json.load(f)
        print(f"[INFO] Already registered! agent_id={existing['agent_id']}")
        print(f"[INFO] tx_hash={existing['tx_hash']}")
        print(f"[INFO] Delete {REGISTRATION_FILE} to re-register.")
        return existing

    print("[INFO] Registering CORTEX on ERC-8004 IdentityRegistry (Sepolia)...")
    print(f"[INFO] Agent URI: {AGENT_URI}")
    print(f"[INFO] Wallet: {client.account.address}")

    result = client.register_agent(AGENT_URI)

    # Save registration
    data = {
        "agent_id":           result["agent_id"],
        "tx_hash":            result["tx_hash"],
        "agent_uri":          AGENT_URI,
        "identity_registry":  "0x8004A818BFB912233c491871b3d84c89A494BD9e",
        "reputation_registry":"0x8004B663056A597Dffe9eCcC1965A193B7388713",
        "network":            "sepolia",
        "explorer_link":      f"https://sepolia.etherscan.io/tx/{result['tx_hash']}"
    }
    with open(REGISTRATION_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\n[SUCCESS] CORTEX registered on ERC-8004!")
    print(f"  agent_id : {result['agent_id']}")
    print(f"  tx_hash  : {result['tx_hash']}")
    print(f"  explorer : https://sepolia.etherscan.io/tx/{result['tx_hash']}")
    print(f"  Saved to : {REGISTRATION_FILE}")
    return data


if __name__ == "__main__":
    main()