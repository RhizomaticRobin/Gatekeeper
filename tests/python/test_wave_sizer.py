"""Tests for dynamic wave sizer (scripts/wave_sizer.py).

Validates:
  - compute_wave_size returns recommended wave size based on task scope and history
  - Wave size decreases when average file scope is large
  - Historical duration data influences grouping decisions
  - max_concurrent is respected as an upper bound
  - Single task returns wave size of 1
  - CLI outputs JSON with wave_size and reasoning
"""

import json
import os
import subprocess
import sys

import pytest
import yaml

# Allow importing from scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from wave_sizer import compute_wave_size


# ---------------------------------------------------------------------------
# Helper: build task dicts that look like plan tasks with owned_files
# ---------------------------------------------------------------------------

def _make_task(task_id, owned_files=None, name=None):
    """Return a minimal task dict with an optional list of owned files."""
    return {
        "id": task_id,
        "name": name or f"Task {task_id}",
        "status": "pending",
        "depends_on": [],
        "owned_files": owned_files or [],
        "deliverables": {"backend": "impl", "frontend": "ui"},
        "tests": {
            "quantitative": {"command": "echo pass"},
            "qualitative": {"criteria": ["works"]},
        },
        "prompt_file": f"tasks/task-{task_id}.md",
    }


# ---------------------------------------------------------------------------
# Test: default wave size (no history) returns max_concurrent
# ---------------------------------------------------------------------------

class TestDefaultWaveSize:
    """When no history is provided, wave size should equal max_concurrent."""

    def test_default_wave_size(self):
        tasks = [_make_task("1.1"), _make_task("1.2"), _make_task("1.3"),
                 _make_task("1.4"), _make_task("1.5")]
        result = compute_wave_size(tasks)
        assert result == 4, (
            f"Expected default wave size of 4 (max_concurrent), got {result}"
        )

    def test_default_wave_size_custom_max(self):
        tasks = [_make_task("1.1"), _make_task("1.2"), _make_task("1.3"),
                 _make_task("1.4"), _make_task("1.5"), _make_task("1.6")]
        result = compute_wave_size(tasks, max_concurrent=6)
        assert result == 6, (
            f"Expected wave size of 6 (custom max_concurrent), got {result}"
        )


# ---------------------------------------------------------------------------
# Test: large scope (20+ owned files) reduces wave size
# ---------------------------------------------------------------------------

class TestLargeScopeReduces:
    """Tasks with 20+ owned files should reduce the wave size below max."""

    def test_large_scope_reduces(self):
        # Each task owns 25 files -- large scope should shrink the wave
        big_files = [f"src/file_{i}.py" for i in range(25)]
        tasks = [_make_task(f"1.{i}", owned_files=big_files) for i in range(1, 6)]

        result = compute_wave_size(tasks, max_concurrent=4)
        assert result < 4, (
            f"Expected wave size < 4 for large-scope tasks, got {result}"
        )
        assert result >= 1, "Wave size must be at least 1"

    def test_small_scope_no_reduction(self):
        # Each task owns only 2 files -- should NOT reduce
        small_files = ["src/a.py", "src/b.py"]
        tasks = [_make_task(f"1.{i}", owned_files=small_files) for i in range(1, 6)]

        result = compute_wave_size(tasks, max_concurrent=4)
        assert result == 4, (
            f"Expected full max_concurrent=4 for small-scope tasks, got {result}"
        )


# ---------------------------------------------------------------------------
# Test: slow history reduces wave size
# ---------------------------------------------------------------------------

class TestSlowHistoryReduces:
    """Historically slow tasks should reduce the recommended wave size."""

    def test_slow_history_reduces(self):
        tasks = [_make_task(f"1.{i}") for i in range(1, 6)]

        # History entries with high durations (avg > 120s)
        history = [
            {"task_id": "1.1", "duration_s": 300.0, "passed": True},
            {"task_id": "1.2", "duration_s": 250.0, "passed": True},
            {"task_id": "1.3", "duration_s": 200.0, "passed": False},
        ]

        result = compute_wave_size(tasks, history=history, max_concurrent=4)
        assert result < 4, (
            f"Expected wave size < 4 for historically slow tasks, got {result}"
        )
        assert result >= 1, "Wave size must be at least 1"

    def test_fast_history_no_reduction(self):
        tasks = [_make_task(f"1.{i}") for i in range(1, 6)]

        # History entries with low durations (avg < 60s)
        history = [
            {"task_id": "1.1", "duration_s": 20.0, "passed": True},
            {"task_id": "1.2", "duration_s": 30.0, "passed": True},
            {"task_id": "1.3", "duration_s": 25.0, "passed": True},
        ]

        result = compute_wave_size(tasks, history=history, max_concurrent=4)
        assert result == 4, (
            f"Expected full max_concurrent=4 for fast tasks, got {result}"
        )


# ---------------------------------------------------------------------------
# Test: max_concurrent is always respected
# ---------------------------------------------------------------------------

class TestMaxConcurrentRespected:
    """Wave size must never exceed max_concurrent."""

    def test_max_concurrent_respected(self):
        # Many small tasks -- should still cap at max_concurrent
        tasks = [_make_task(f"1.{i}") for i in range(1, 20)]

        result = compute_wave_size(tasks, max_concurrent=3)
        assert result <= 3, (
            f"Wave size {result} exceeds max_concurrent=3"
        )

    def test_max_concurrent_one(self):
        tasks = [_make_task("1.1"), _make_task("1.2")]
        result = compute_wave_size(tasks, max_concurrent=1)
        assert result == 1, (
            f"Expected wave size 1 with max_concurrent=1, got {result}"
        )


# ---------------------------------------------------------------------------
# Test: single task returns 1
# ---------------------------------------------------------------------------

class TestSingleTask:
    """A single task should always produce wave size 1."""

    def test_single_task(self):
        tasks = [_make_task("1.1")]
        result = compute_wave_size(tasks, max_concurrent=4)
        assert result == 1, (
            f"Expected wave size 1 for single task, got {result}"
        )

    def test_single_task_with_history(self):
        tasks = [_make_task("1.1")]
        history = [{"task_id": "1.1", "duration_s": 10.0, "passed": True}]
        result = compute_wave_size(tasks, history=history, max_concurrent=4)
        assert result == 1, (
            f"Expected wave size 1 for single task even with history, got {result}"
        )


# ---------------------------------------------------------------------------
# Test: CLI outputs JSON with wave_size and reasoning
# ---------------------------------------------------------------------------

class TestCLI:
    """CLI should output valid JSON with wave_size and reasoning keys."""

    def test_cli_json_output(self, tmp_path):
        # Create a minimal plan.yaml with enough tasks
        plan = {
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
                    "tasks": [
                        {
                            "id": "1.1",
                            "name": "Task A",
                            "status": "pending",
                            "depends_on": [],
                            "owned_files": ["a.py"],
                            "deliverables": {"backend": "b", "frontend": "f"},
                            "tests": {
                                "quantitative": {"command": "echo pass"},
                                "qualitative": {"criteria": ["ok"]},
                            },
                            "prompt_file": "tasks/task-1.1.md",
                        },
                        {
                            "id": "1.2",
                            "name": "Task B",
                            "status": "pending",
                            "depends_on": [],
                            "owned_files": ["b.py"],
                            "deliverables": {"backend": "b", "frontend": "f"},
                            "tests": {
                                "quantitative": {"command": "echo pass"},
                                "qualitative": {"criteria": ["ok"]},
                            },
                            "prompt_file": "tasks/task-1.2.md",
                        },
                    ],
                },
            ],
        }
        plan_path = tmp_path / "plan.yaml"
        with open(plan_path, "w") as f:
            yaml.dump(plan, f, default_flow_style=False)

        script_path = os.path.join(
            os.path.dirname(__file__), "../../scripts/wave_sizer.py"
        )
        result = subprocess.run(
            [sys.executable, script_path, str(plan_path), "--max-concurrent", "4"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"CLI exited with code {result.returncode}: {result.stderr}"
        )

        output = json.loads(result.stdout.strip())
        assert "wave_size" in output, "CLI output missing 'wave_size' key"
        assert "reasoning" in output, "CLI output missing 'reasoning' key"
        assert isinstance(output["wave_size"], int), "wave_size must be int"
        assert isinstance(output["reasoning"], str), "reasoning must be str"
        assert output["wave_size"] >= 1, "wave_size must be at least 1"
