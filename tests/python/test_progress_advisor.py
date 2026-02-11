"""Tests for progress-aware decision making (scripts/progress_advisor.py).

Validates:
  - compute_progress returns 0% when no tasks are completed
  - compute_progress returns 50% when half of tasks are completed
  - find_critical_path identifies the longest dependency chain
  - advise returns normal prioritization advice when progress < 70%
  - advise returns blocker-focused advice when progress > 70%
  - advise returns a completion message when progress is 100%
"""

import json
import os
import subprocess
import sys

import pytest
import yaml

# Allow importing from scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from progress_advisor import compute_progress, find_critical_path, advise


# ---------------------------------------------------------------------------
# Helper: build plan dicts for testing
# ---------------------------------------------------------------------------

def _make_plan(task_statuses, dependencies=None):
    """Build a minimal plan dict from a list of (task_id, status) pairs.

    Args:
        task_statuses: list of (task_id, status) tuples e.g. [("1.1", "completed"), ...]
        dependencies: optional dict mapping task_id -> list of depends_on ids
    Returns:
        plan dict suitable for compute_progress / find_critical_path / advise
    """
    if dependencies is None:
        dependencies = {}
    tasks = []
    for tid, status in task_statuses:
        tasks.append({
            "id": tid,
            "name": f"Task {tid}",
            "status": status,
            "depends_on": dependencies.get(tid, []),
            "deliverables": {"backend": f"impl {tid}"},
            "tests": {
                "quantitative": {"command": "echo pass"},
                "qualitative": {"criteria": ["works"]},
            },
            "prompt_file": f"tasks/task-{tid}.md",
        })
    return {
        "metadata": {
            "project": "test-project",
            "dev_server_command": "echo ok",
            "dev_server_url": "http://localhost:3000",
            "model_profile": "default",
        },
        "phases": [
            {
                "id": 1,
                "name": "Phase 1",
                "tasks": tasks,
            }
        ],
    }


# ---------------------------------------------------------------------------
# Test: compute_progress returns 0% when no tasks are completed
# ---------------------------------------------------------------------------

class TestProgress0:
    """compute_progress should return 0 when no tasks are completed."""

    def test_progress_0_all_pending(self):
        plan = _make_plan([
            ("1.1", "pending"),
            ("1.2", "pending"),
            ("1.3", "pending"),
            ("1.4", "pending"),
        ])
        result = compute_progress(plan)
        assert result == 0.0, (
            f"Expected 0% progress when no tasks completed, got {result}"
        )

    def test_progress_0_empty_phases(self):
        plan = {
            "metadata": {"project": "empty"},
            "phases": [],
        }
        result = compute_progress(plan)
        assert result == 0.0, (
            f"Expected 0% for plan with no tasks, got {result}"
        )


# ---------------------------------------------------------------------------
# Test: compute_progress returns 50% when half completed
# ---------------------------------------------------------------------------

class TestProgress50:
    """compute_progress should return 50 when half of tasks are completed."""

    def test_progress_50(self):
        plan = _make_plan([
            ("1.1", "completed"),
            ("1.2", "completed"),
            ("1.3", "pending"),
            ("1.4", "pending"),
        ])
        result = compute_progress(plan)
        assert result == 50.0, (
            f"Expected 50% progress when 2/4 tasks completed, got {result}"
        )

    def test_progress_100(self):
        plan = _make_plan([
            ("1.1", "completed"),
            ("1.2", "completed"),
        ])
        result = compute_progress(plan)
        assert result == 100.0, (
            f"Expected 100% when all tasks completed, got {result}"
        )

    def test_progress_partial(self):
        plan = _make_plan([
            ("1.1", "completed"),
            ("1.2", "pending"),
            ("1.3", "pending"),
        ])
        result = compute_progress(plan)
        # 1/3 = 33.33...
        assert abs(result - 33.33) < 0.5, (
            f"Expected ~33.33% when 1/3 tasks completed, got {result}"
        )


# ---------------------------------------------------------------------------
# Test: find_critical_path — longest dependency chain identified
# ---------------------------------------------------------------------------

class TestCriticalPath:
    """find_critical_path should return the longest dependency chain."""

    def test_critical_path_linear_chain(self):
        """A -> B -> C -> D: critical path length = 4."""
        deps = {
            "1.1": [],
            "1.2": ["1.1"],
            "1.3": ["1.2"],
            "1.4": ["1.3"],
        }
        plan = _make_plan([
            ("1.1", "pending"),
            ("1.2", "pending"),
            ("1.3", "pending"),
            ("1.4", "pending"),
        ], dependencies=deps)

        path = find_critical_path(plan)
        assert isinstance(path, list), "Critical path should be a list"
        assert len(path) == 4, (
            f"Expected critical path length 4 for linear chain, got {len(path)}"
        )
        # The path should be ordered from start to end
        assert path == ["1.1", "1.2", "1.3", "1.4"], (
            f"Expected ['1.1','1.2','1.3','1.4'], got {path}"
        )

    def test_critical_path_diamond(self):
        """Diamond shape: A -> B, A -> C, B -> D, C -> D.
        Longest path is A -> B -> D or A -> C -> D (length 3)."""
        deps = {
            "1.1": [],
            "1.2": ["1.1"],
            "1.3": ["1.1"],
            "1.4": ["1.2", "1.3"],
        }
        plan = _make_plan([
            ("1.1", "pending"),
            ("1.2", "pending"),
            ("1.3", "pending"),
            ("1.4", "pending"),
        ], dependencies=deps)

        path = find_critical_path(plan)
        assert isinstance(path, list), "Critical path should be a list"
        assert len(path) == 3, (
            f"Expected critical path length 3 for diamond, got {len(path)}"
        )
        # Path must start at 1.1 and end at 1.4
        assert path[0] == "1.1", f"Critical path should start at 1.1, got {path[0]}"
        assert path[-1] == "1.4", f"Critical path should end at 1.4, got {path[-1]}"

    def test_critical_path_no_deps(self):
        """When no dependencies, critical path length should be 1."""
        plan = _make_plan([
            ("1.1", "pending"),
            ("1.2", "pending"),
            ("1.3", "pending"),
        ])

        path = find_critical_path(plan)
        assert isinstance(path, list), "Critical path should be a list"
        assert len(path) == 1, (
            f"Expected critical path length 1 when no deps, got {len(path)}"
        )

    def test_critical_path_empty_plan(self):
        """Empty plan has empty critical path."""
        plan = {"metadata": {"project": "empty"}, "phases": []}
        path = find_critical_path(plan)
        assert isinstance(path, list), "Critical path should be a list"
        assert len(path) == 0, (
            f"Expected empty critical path for empty plan, got {path}"
        )


# ---------------------------------------------------------------------------
# Test: advise returns normal prioritization when < 70%
# ---------------------------------------------------------------------------

class TestAdviceEarly:
    """advise should return normal prioritization advice when progress < 70%."""

    def test_advice_early_normal_prioritization(self):
        plan = _make_plan([
            ("1.1", "completed"),
            ("1.2", "pending"),
            ("1.3", "pending"),
            ("1.4", "pending"),
            ("1.5", "pending"),
        ])
        result = advise(plan)
        assert isinstance(result, dict), "advise should return a dict"
        assert "progress" in result, "Result should contain 'progress' key"
        assert "advice" in result, "Result should contain 'advice' key"
        assert result["progress"] < 70.0, (
            f"Test setup error: progress should be < 70, got {result['progress']}"
        )
        # Advice text should exist and not mention blocker-focus
        advice_text = result["advice"]
        assert isinstance(advice_text, str), "advice should be a string"
        assert len(advice_text) > 0, "advice should not be empty"

    def test_advice_early_has_critical_path(self):
        deps = {"1.2": ["1.1"], "1.3": ["1.2"]}
        plan = _make_plan([
            ("1.1", "pending"),
            ("1.2", "pending"),
            ("1.3", "pending"),
        ], dependencies=deps)
        result = advise(plan)
        assert "critical_path" in result, "Result should contain 'critical_path' key"
        assert isinstance(result["critical_path"], list), "critical_path should be a list"


# ---------------------------------------------------------------------------
# Test: advise returns blocker-focused advice when > 70%
# ---------------------------------------------------------------------------

class TestAdviceLate:
    """advise should focus on remaining blockers when progress exceeds 70%."""

    def test_advice_late_blocker_focus(self):
        # 8 out of 10 tasks done = 80%
        task_statuses = [(f"1.{i}", "completed") for i in range(1, 9)]
        task_statuses += [("1.9", "pending"), ("1.10", "pending")]
        deps = {"1.10": ["1.9"]}
        plan = _make_plan(task_statuses, dependencies=deps)

        result = advise(plan)
        assert result["progress"] > 70.0, (
            f"Test setup error: progress should be > 70, got {result['progress']}"
        )
        advice_text = result["advice"].lower()
        # The advice should mention blockers or remaining or focus
        assert any(word in advice_text for word in ["blocker", "remaining", "focus", "block"]), (
            f"Late-stage advice should mention blockers/remaining/focus. Got: {result['advice']}"
        )

    def test_advice_late_differs_from_early(self):
        # Early plan: 1 out of 10 done = 10%
        early_statuses = [("1.1", "completed")] + [(f"1.{i}", "pending") for i in range(2, 11)]
        early_plan = _make_plan(early_statuses)

        # Late plan: 8 out of 10 done = 80%
        late_statuses = [(f"1.{i}", "completed") for i in range(1, 9)]
        late_statuses += [("1.9", "pending"), ("1.10", "pending")]
        late_plan = _make_plan(late_statuses)

        early_result = advise(early_plan)
        late_result = advise(late_plan)

        # The advice text must differ between early and late stages
        assert early_result["advice"] != late_result["advice"], (
            "Advice should change between early (<70%) and late (>70%) stages"
        )


# ---------------------------------------------------------------------------
# Test: advise returns completion message when 100%
# ---------------------------------------------------------------------------

class TestAdviceAllDone:
    """advise should return a completion message when all tasks are done."""

    def test_advice_all_done_completion_message(self):
        plan = _make_plan([
            ("1.1", "completed"),
            ("1.2", "completed"),
            ("1.3", "completed"),
        ])
        result = advise(plan)
        assert result["progress"] == 100.0, (
            f"Expected 100% progress, got {result['progress']}"
        )
        advice_text = result["advice"].lower()
        assert any(word in advice_text for word in ["complete", "done", "finished", "all tasks"]), (
            f"100% advice should indicate completion. Got: {result['advice']}"
        )

    def test_advice_all_done_no_blockers(self):
        plan = _make_plan([
            ("1.1", "completed"),
            ("1.2", "completed"),
        ])
        result = advise(plan)
        # When everything is done, there should be no remaining blockers
        assert result["progress"] == 100.0


# ---------------------------------------------------------------------------
# Test: CLI interface
# ---------------------------------------------------------------------------

class TestCLI:
    """CLI should output valid JSON with progress and advice."""

    def test_cli_json_output(self, tmp_path):
        plan = _make_plan([
            ("1.1", "completed"),
            ("1.2", "pending"),
            ("1.3", "pending"),
            ("1.4", "pending"),
        ])
        plan_path = tmp_path / "plan.yaml"
        with open(plan_path, "w") as f:
            yaml.dump(plan, f, default_flow_style=False)

        script_path = os.path.join(
            os.path.dirname(__file__), "../../scripts/progress_advisor.py"
        )
        result = subprocess.run(
            [sys.executable, script_path, str(plan_path)],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"CLI exited with code {result.returncode}: {result.stderr}"
        )

        output = json.loads(result.stdout.strip())
        assert "progress" in output, "CLI output missing 'progress' key"
        assert "advice" in output, "CLI output missing 'advice' key"
        assert "critical_path" in output, "CLI output missing 'critical_path' key"
        assert isinstance(output["progress"], (int, float)), "progress must be numeric"
        assert isinstance(output["advice"], str), "advice must be a string"
        assert isinstance(output["critical_path"], list), "critical_path must be a list"
