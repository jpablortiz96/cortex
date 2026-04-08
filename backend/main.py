"""
CORTEX — Main Entry Point
Run the autonomous trading desk from terminal.

Usage:
    python main.py                  # Run 3 cycles
    python main.py --cycles 5      # Run 5 cycles
    python main.py --delay 10      # 10 seconds between cycles
"""

import asyncio
import argparse
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator import Orchestrator


def main():
    parser = argparse.ArgumentParser(description="CORTEX — Autonomous Trading Desk")
    parser.add_argument("--cycles", type=int, default=3, help="Number of trading cycles to run")
    parser.add_argument("--delay", type=int, default=5, help="Seconds between cycles")
    parser.add_argument("--capital", type=float, default=10000.0, help="Initial capital in USD")
    args = parser.parse_args()

    # Check for API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("[ERROR] ERROR: ANTHROPIC_API_KEY not set.")
        print()
        print("Set it with:")
        print("  export ANTHROPIC_API_KEY='your-key-here'")
        print()
        sys.exit(1)

    print(f"[KEY] API key found: {api_key[:8]}...{api_key[-4:]}")

    desk = Orchestrator(initial_capital=args.capital)
    asyncio.run(desk.run(num_cycles=args.cycles, delay_seconds=args.delay))


if __name__ == "__main__":
    main()
