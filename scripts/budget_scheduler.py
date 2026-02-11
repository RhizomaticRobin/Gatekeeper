#!/usr/bin/env python3
"""Budget-aware scheduling for GSD-VGL concurrent task execution.

Reads budget status from Ralph's budget.sh output and adjusts agent
concurrency proportionally:
  - 100% budget -> max_agents (default 4)
  - 30% budget  -> 2 agents (reduced concurrency)
  - 10% budget  -> 1 agent (single-agent mode)
  - 5% budget   -> 0 agents (halt dispatching)

Functions:
  get_budget_status()                -> int (remaining percentage, 0-100)
  should_reduce_concurrency(pct)     -> bool (True when budget <= 30%)
  get_max_agents(pct, max_agents=4)  -> int (scaled agent count)

CLI:
  python3 budget_scheduler.py --status       # prints budget percentage
  python3 budget_scheduler.py --max-agents   # prints recommended agent count
"""

import argparse
import os
import re
import subprocess
import sys


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_LOW_BUDGET_THRESHOLD = 30     # percentage at or below which concurrency is reduced
_CRITICAL_BUDGET_THRESHOLD = 10  # percentage at or below which single-agent mode
_EXHAUSTED_BUDGET_THRESHOLD = 5  # percentage at or below which zero agents dispatched


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def get_budget_status():
    """Call bin/lib/budget.sh and parse output for remaining budget percentage.

    Returns:
        int: Budget remaining as a percentage (0-100).
             Returns 100 (safe default) if budget.sh is unavailable or
             output cannot be parsed.
    """
    try:
        # Locate budget.sh relative to this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        budget_script = os.path.join(project_root, "bin", "lib", "budget.sh")

        result = subprocess.run(
            ["bash", budget_script, "--status"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return 100  # Safe default on failure

        return _parse_budget_output(result.stdout)

    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return 100  # Safe default when script is unavailable


def _parse_budget_output(output):
    """Parse budget.sh output for a percentage value.

    Looks for patterns like:
      - "Budget remaining: 75%"
      - "remaining: 42%"
      - Any line containing a number followed by %

    Args:
        output: stdout string from budget.sh

    Returns:
        int: Parsed percentage, or 100 if no percentage found.
    """
    if not output:
        return 100

    # Look for "Budget remaining: NN%" pattern first
    match = re.search(r'[Bb]udget\s+remaining:\s*(\d+)%', output)
    if match:
        return int(match.group(1))

    # Fallback: look for any "NN%" pattern
    match = re.search(r'(\d+)%', output)
    if match:
        return int(match.group(1))

    return 100  # Safe default if no percentage found


def should_reduce_concurrency(budget_pct):
    """Check whether concurrency should be reduced based on budget.

    Args:
        budget_pct: Budget remaining as a percentage (0-100).

    Returns:
        bool: True when budget is at or below the low threshold (30%).
    """
    return budget_pct <= _LOW_BUDGET_THRESHOLD


def get_max_agents(budget_remaining, max_agents=4, emit_warnings=False):
    """Compute the maximum number of agents to dispatch based on budget.

    Scaling rules:
      - budget > 30%:  full concurrency (max_agents)
      - 10% < budget <= 30%: reduced to 2
      - 5% < budget <= 10%: single agent (1)
      - budget <= 5%: zero agents (halt)

    Args:
        budget_remaining: Budget remaining as percentage (0-100).
        max_agents: Upper bound on concurrency (default 4).
        emit_warnings: If True, print warnings to stderr at thresholds.

    Returns:
        int: Number of agents to dispatch (0 to max_agents).
    """
    if budget_remaining <= _EXHAUSTED_BUDGET_THRESHOLD:
        if emit_warnings:
            print(
                f"Budget exhausted ({budget_remaining}%) "
                f"-- zero agents dispatched",
                file=sys.stderr,
            )
        return 0

    if budget_remaining <= _CRITICAL_BUDGET_THRESHOLD:
        if emit_warnings:
            print(
                f"Budget critical ({budget_remaining}%) "
                f"-- single agent only",
                file=sys.stderr,
            )
        return 1

    if budget_remaining <= _LOW_BUDGET_THRESHOLD:
        if emit_warnings:
            print(
                f"Budget low ({budget_remaining}%) "
                f"-- reducing concurrency",
                file=sys.stderr,
            )
        return 2

    # Budget is healthy (> 30%)
    return max_agents


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """CLI entry point.

    Usage:
      python3 budget_scheduler.py --status       # prints budget %
      python3 budget_scheduler.py --max-agents   # prints agent count
    """
    parser = argparse.ArgumentParser(
        description="Budget-aware scheduling for GSD-VGL"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--status",
        action="store_true",
        help="Print current budget remaining percentage",
    )
    group.add_argument(
        "--max-agents",
        action="store_true",
        help="Print recommended number of agents to dispatch",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=4,
        help="Maximum concurrency upper bound (default: 4)",
    )

    args = parser.parse_args()

    budget_pct = get_budget_status()

    if args.status:
        print(budget_pct)
    elif args.max_agents:
        agents = get_max_agents(
            budget_pct,
            max_agents=args.max_concurrent,
            emit_warnings=True,
        )
        print(agents)


if __name__ == "__main__":
    main()
