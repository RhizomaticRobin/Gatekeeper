"""Tests for pattern recognition and strategy adaptation (Task 2.5).

Tests:
  - detect_patterns finds recurring failures grouped by file scope and error type
  - Patterns are project-scoped (stored per-project, not global)
  - get_strategy_advice returns iteration_budget and prompt_additions based on patterns
  - Strategy advice degrades gracefully when no history exists
"""

import hashlib
import json
import os
import sys
import tempfile

import pytest

# Ensure scripts/ is importable
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
sys.path.insert(0, os.path.abspath(SCRIPTS_DIR))

from run_history import detect_patterns, record_outcome, get_all_history
from learnings import get_strategy_advice


@pytest.fixture
def history_dir(tmp_path):
    """Provide a temporary history directory."""
    hdir = tmp_path / "history"
    hdir.mkdir()
    return str(hdir)


def _file_scope_hash(file_path):
    """Compute the same hash that detect_patterns uses for file scope."""
    return hashlib.sha256(file_path.encode()).hexdigest()[:12]


def _build_history_with_repeated_failures(history_dir, file_scope, error_category, count):
    """Record `count` failed runs with the same file_scope and error_category."""
    for i in range(count):
        record_outcome(
            task_id=f"task-{i}",
            iterations=5,
            passed=False,
            duration_seconds=60.0,
            failure_reasons=[f"{error_category}: failure in {file_scope}"],
            session_id=f"sess-{i}",
            history_dir=history_dir,
        )


# ---------------------------------------------------------------------------
# detect_patterns tests
# ---------------------------------------------------------------------------

class TestDetectPatterns:
    """Tests for detect_patterns(history, min_occurrences)."""

    def test_detect_patterns_found(self, history_dir):
        """3+ failures with same scope/type are detected as a pattern."""
        file_scope = "src/components/Button.tsx"
        error_category = "TypeError"

        _build_history_with_repeated_failures(
            history_dir, file_scope, error_category, count=4
        )
        history = get_all_history(history_dir=history_dir)
        patterns = detect_patterns(history, min_occurrences=3)

        assert len(patterns) >= 1
        # Find the pattern matching our file_scope and error_category
        matching = [
            p for p in patterns
            if file_scope in p.get("file_scope", "")
            and error_category in p.get("error_category", "")
        ]
        assert len(matching) == 1, f"Expected 1 matching pattern, got {matching}"
        pattern = matching[0]
        assert pattern["count"] >= 3
        assert "file_scope" in pattern
        assert "error_category" in pattern

    def test_detect_patterns_below_threshold(self, history_dir):
        """2 occurrences should NOT be flagged with default min_occurrences=3."""
        file_scope = "src/utils/helpers.py"
        error_category = "ImportError"

        _build_history_with_repeated_failures(
            history_dir, file_scope, error_category, count=2
        )
        history = get_all_history(history_dir=history_dir)
        patterns = detect_patterns(history, min_occurrences=3)

        # No pattern should be found with only 2 occurrences
        matching = [
            p for p in patterns
            if file_scope in p.get("file_scope", "")
            and error_category in p.get("error_category", "")
        ]
        assert len(matching) == 0, f"Should not flag below threshold, got {matching}"

    def test_detect_patterns_empty_history(self):
        """Empty history returns empty list of patterns."""
        patterns = detect_patterns([], min_occurrences=3)
        assert patterns == []

    def test_detect_patterns_multiple_groups(self, history_dir):
        """Different file/error combos are grouped separately."""
        # Group A: 3 failures
        _build_history_with_repeated_failures(
            history_dir, "src/api/auth.py", "ValueError", count=3
        )
        # Group B: 3 failures
        _build_history_with_repeated_failures(
            history_dir, "src/api/auth.py", "KeyError", count=3
        )
        history = get_all_history(history_dir=history_dir)
        patterns = detect_patterns(history, min_occurrences=3)

        # Should detect both patterns separately
        assert len(patterns) >= 2


# ---------------------------------------------------------------------------
# get_strategy_advice tests
# ---------------------------------------------------------------------------

class TestGetStrategyAdvice:
    """Tests for get_strategy_advice(task_context, patterns, history)."""

    def test_strategy_advice_known_difficult(self, history_dir):
        """iteration_budget is increased for a task matching a known-difficult pattern."""
        file_scope = "src/components/Form.tsx"
        error_category = "RenderError"

        _build_history_with_repeated_failures(
            history_dir, file_scope, error_category, count=5
        )
        history = get_all_history(history_dir=history_dir)
        patterns = detect_patterns(history, min_occurrences=3)

        task_context = {
            "file_patterns": [file_scope],
            "task_type": "frontend",
        }

        advice = get_strategy_advice(task_context, patterns, history)

        assert "iteration_budget" in advice
        # Budget should be higher than default (default is typically 3)
        assert advice["iteration_budget"] > 3

    def test_strategy_advice_no_patterns(self):
        """Default budget returned when no patterns exist."""
        task_context = {
            "file_patterns": ["src/new_file.py"],
            "task_type": "backend",
        }

        advice = get_strategy_advice(task_context, patterns=[], history=[])

        assert "iteration_budget" in advice
        # Default budget
        assert advice["iteration_budget"] == 3
        assert "prompt_additions" in advice

    def test_strategy_advice_prompt_additions(self, history_dir):
        """Warning text is added to prompt_additions for matching patterns."""
        file_scope = "src/services/payment.py"
        error_category = "TimeoutError"

        _build_history_with_repeated_failures(
            history_dir, file_scope, error_category, count=4
        )
        history = get_all_history(history_dir=history_dir)
        patterns = detect_patterns(history, min_occurrences=3)

        task_context = {
            "file_patterns": [file_scope],
            "task_type": "backend",
        }

        advice = get_strategy_advice(task_context, patterns, history)

        assert "prompt_additions" in advice
        assert isinstance(advice["prompt_additions"], list)
        assert len(advice["prompt_additions"]) >= 1
        # The prompt additions should contain relevant warning text
        combined = " ".join(advice["prompt_additions"])
        assert "TimeoutError" in combined or "pattern" in combined.lower()
