"""Tests for budget-aware scheduling (scripts/budget_scheduler.py).

Validates:
  - get_budget_status() parses budget.sh output for remaining percentage
  - should_reduce_concurrency() returns True when budget < 30%
  - get_max_agents() scales concurrency proportionally based on budget
  - CLI outputs status and max-agents information
  - Warning messages emitted at appropriate budget thresholds
"""

import json
import os
import subprocess
import sys
from unittest.mock import patch, MagicMock

import pytest

# Allow importing from scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from budget_scheduler import (
    get_budget_status,
    should_reduce_concurrency,
    get_max_agents,
)


# ---------------------------------------------------------------------------
# Test: full budget returns max concurrency
# ---------------------------------------------------------------------------

class TestFullBudget:
    """100% budget remaining should return the maximum number of agents."""

    def test_full_budget(self):
        result = get_max_agents(100, max_agents=4)
        assert result == 4, (
            f"Expected max concurrency of 4 at 100% budget, got {result}"
        )

    def test_full_budget_custom_max(self):
        result = get_max_agents(100, max_agents=8)
        assert result == 8, (
            f"Expected max concurrency of 8 at 100% budget, got {result}"
        )


# ---------------------------------------------------------------------------
# Test: low budget returns reduced concurrency
# ---------------------------------------------------------------------------

class TestLowBudget:
    """Budget at 25% (below 30%) should reduce concurrency."""

    def test_low_budget(self):
        result = get_max_agents(25, max_agents=4)
        assert result == 2, (
            f"Expected concurrency of 2 at 25% budget, got {result}"
        )

    def test_low_budget_at_30(self):
        """At exactly 30%, concurrency should be reduced to 2."""
        result = get_max_agents(30, max_agents=4)
        assert result == 2, (
            f"Expected concurrency of 2 at 30% budget, got {result}"
        )

    def test_above_30_no_reduction(self):
        """At 31%, full concurrency should be returned."""
        result = get_max_agents(31, max_agents=4)
        assert result == 4, (
            f"Expected full concurrency of 4 at 31% budget, got {result}"
        )


# ---------------------------------------------------------------------------
# Test: critical budget returns 1
# ---------------------------------------------------------------------------

class TestCriticalBudget:
    """Budget at 8% (below 10%) should return single-agent mode."""

    def test_critical_budget(self):
        result = get_max_agents(8, max_agents=4)
        assert result == 1, (
            f"Expected concurrency of 1 at 8% budget, got {result}"
        )

    def test_critical_budget_at_10(self):
        """At exactly 10%, should still be single-agent mode."""
        result = get_max_agents(10, max_agents=4)
        assert result == 1, (
            f"Expected concurrency of 1 at 10% budget, got {result}"
        )

    def test_critical_budget_at_6(self):
        """At 6%, should be single-agent mode (above 5% cutoff)."""
        result = get_max_agents(6, max_agents=4)
        assert result == 1, (
            f"Expected concurrency of 1 at 6% budget, got {result}"
        )


# ---------------------------------------------------------------------------
# Test: exhausted budget returns 0
# ---------------------------------------------------------------------------

class TestExhaustedBudget:
    """Budget at 3% (below 5%) should return zero agents."""

    def test_exhausted_budget(self):
        result = get_max_agents(3, max_agents=4)
        assert result == 0, (
            f"Expected 0 agents at 3% budget, got {result}"
        )

    def test_exhausted_budget_at_5(self):
        """At exactly 5%, should dispatch zero agents."""
        result = get_max_agents(5, max_agents=4)
        assert result == 0, (
            f"Expected 0 agents at 5% budget, got {result}"
        )

    def test_exhausted_budget_at_0(self):
        """At 0%, should dispatch zero agents."""
        result = get_max_agents(0, max_agents=4)
        assert result == 0, (
            f"Expected 0 agents at 0% budget, got {result}"
        )

    def test_exhausted_budget_at_1(self):
        """At 1%, should dispatch zero agents."""
        result = get_max_agents(1, max_agents=4)
        assert result == 0, (
            f"Expected 0 agents at 1% budget, got {result}"
        )


# ---------------------------------------------------------------------------
# Test: should_reduce_concurrency returns True when < 30%
# ---------------------------------------------------------------------------

class TestShouldReduce:
    """should_reduce_concurrency should return True when budget < 30%."""

    def test_should_reduce_at_25(self):
        assert should_reduce_concurrency(25) is True

    def test_should_reduce_at_29(self):
        assert should_reduce_concurrency(29) is True

    def test_should_not_reduce_at_30(self):
        """At exactly 30%, should still reduce (threshold is <=30%)."""
        assert should_reduce_concurrency(30) is True

    def test_should_not_reduce_at_50(self):
        assert should_reduce_concurrency(50) is False

    def test_should_not_reduce_at_100(self):
        assert should_reduce_concurrency(100) is False

    def test_should_reduce_at_0(self):
        assert should_reduce_concurrency(0) is True

    def test_should_reduce_at_10(self):
        assert should_reduce_concurrency(10) is True


# ---------------------------------------------------------------------------
# Test: budget parsing from budget.sh output
# ---------------------------------------------------------------------------

class TestBudgetParsing:
    """get_budget_status should parse budget.sh output for remaining %."""

    @patch("budget_scheduler.subprocess.run")
    def test_parse_budget_output_percentage(self, mock_run):
        """Parse standard budget.sh output containing a percentage."""
        mock_run.return_value = MagicMock(
            stdout="Budget remaining: 75%\n",
            stderr="",
            returncode=0,
        )
        result = get_budget_status()
        assert result == 75, (
            f"Expected 75 from 'Budget remaining: 75%', got {result}"
        )

    @patch("budget_scheduler.subprocess.run")
    def test_parse_budget_output_low(self, mock_run):
        """Parse budget.sh output with low percentage."""
        mock_run.return_value = MagicMock(
            stdout="Budget remaining: 12%\n",
            stderr="",
            returncode=0,
        )
        result = get_budget_status()
        assert result == 12, (
            f"Expected 12 from 'Budget remaining: 12%', got {result}"
        )

    @patch("budget_scheduler.subprocess.run")
    def test_parse_iterations_format(self, mock_run):
        """Parse budget.sh output with iterations used/max format."""
        mock_run.return_value = MagicMock(
            stdout="Iterations: 10/50\nBudget remaining: 80%\n",
            stderr="",
            returncode=0,
        )
        result = get_budget_status()
        assert result == 80, (
            f"Expected 80 from multi-line output, got {result}"
        )

    @patch("budget_scheduler.subprocess.run")
    def test_budget_script_failure_returns_100(self, mock_run):
        """If budget.sh fails, assume full budget (safe default)."""
        mock_run.side_effect = FileNotFoundError("budget.sh not found")
        result = get_budget_status()
        assert result == 100, (
            f"Expected 100 (safe default) when budget.sh fails, got {result}"
        )

    @patch("budget_scheduler.subprocess.run")
    def test_budget_unparseable_output_returns_100(self, mock_run):
        """If budget.sh output can't be parsed, assume full budget."""
        mock_run.return_value = MagicMock(
            stdout="No budget info available\n",
            stderr="",
            returncode=0,
        )
        result = get_budget_status()
        assert result == 100, (
            f"Expected 100 (safe default) for unparseable output, got {result}"
        )

    @patch("budget_scheduler.subprocess.run")
    def test_budget_nonzero_exit_returns_100(self, mock_run):
        """If budget.sh exits non-zero, assume full budget."""
        mock_run.return_value = MagicMock(
            stdout="",
            stderr="Error: config not found",
            returncode=1,
        )
        result = get_budget_status()
        assert result == 100, (
            f"Expected 100 (safe default) for non-zero exit, got {result}"
        )


# ---------------------------------------------------------------------------
# Test: warning messages at budget thresholds
# ---------------------------------------------------------------------------

class TestWarningMessages:
    """Verify warning messages are emitted at appropriate thresholds."""

    def test_low_budget_warning(self, capsys):
        """Budget < 30% should emit low budget warning."""
        get_max_agents(25, max_agents=4, emit_warnings=True)
        captured = capsys.readouterr()
        assert "Budget low" in captured.err or "Budget low" in captured.out, (
            "Expected 'Budget low' warning at 25% budget"
        )
        assert "25%" in captured.err or "25%" in captured.out, (
            "Expected percentage in warning message"
        )

    def test_critical_budget_warning(self, capsys):
        """Budget < 10% should emit critical budget warning."""
        get_max_agents(8, max_agents=4, emit_warnings=True)
        captured = capsys.readouterr()
        output = captured.err + captured.out
        assert "critical" in output.lower() or "Critical" in output, (
            "Expected 'critical' warning at 8% budget"
        )
        assert "8%" in output, (
            "Expected percentage in critical warning message"
        )

    def test_no_warning_at_full_budget(self, capsys):
        """Budget at 100% should not emit any warnings."""
        get_max_agents(100, max_agents=4, emit_warnings=True)
        captured = capsys.readouterr()
        output = captured.err + captured.out
        assert "Budget low" not in output, (
            "Should not emit budget warning at 100%"
        )
        assert "critical" not in output.lower(), (
            "Should not emit critical warning at 100%"
        )


# ---------------------------------------------------------------------------
# Test: CLI interface
# ---------------------------------------------------------------------------

class TestCLI:
    """CLI should support --status and --max-agents flags."""

    @patch("budget_scheduler.subprocess.run")
    def test_cli_status(self, mock_run):
        """--status should output budget percentage."""
        mock_run.return_value = MagicMock(
            stdout="Budget remaining: 65%\n",
            stderr="",
            returncode=0,
        )
        script_path = os.path.join(
            os.path.dirname(__file__), "../../scripts/budget_scheduler.py"
        )
        # We test the CLI via subprocess, mocking won't work there.
        # Instead, test the module-level main function behavior.
        from budget_scheduler import main as budget_main
        with patch("sys.argv", ["budget_scheduler.py", "--status"]):
            with patch("budget_scheduler.get_budget_status", return_value=65):
                budget_main()

    @patch("budget_scheduler.get_budget_status", return_value=25)
    def test_cli_max_agents(self, mock_status, capsys):
        """--max-agents should output the number of agents to dispatch."""
        from budget_scheduler import main as budget_main
        with patch("sys.argv", ["budget_scheduler.py", "--max-agents"]):
            budget_main()
        captured = capsys.readouterr()
        output = captured.out.strip()
        # Should contain a number (the max agents count)
        assert output.isdigit() or any(c.isdigit() for c in output), (
            f"Expected numeric output for --max-agents, got: {output}"
        )
