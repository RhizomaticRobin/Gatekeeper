"""Tests for task type detection and agent routing (scripts/task_router.py).

Validates:
  - detect_task_type correctly classifies tasks by file patterns
  - get_agent_guidance returns different prompt additions per type
  - Unknown patterns default to general type
"""

import json
import os
import subprocess
import sys

import pytest
import yaml

# Allow importing from scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from task_router import detect_task_type, get_agent_guidance


# ---------------------------------------------------------------------------
# Helper: build task dicts with file_scope.owns patterns
# ---------------------------------------------------------------------------

def _make_task(task_id, owns=None, name=None):
    """Return a minimal task dict with an optional file_scope.owns list."""
    task = {
        "id": task_id,
        "name": name or f"Task {task_id}",
        "status": "pending",
        "depends_on": [],
        "deliverables": {"backend": "impl", "frontend": "ui"},
        "tests": {
            "quantitative": {"command": "echo pass"},
            "qualitative": {"criteria": ["works"]},
        },
        "prompt_file": f"tasks/task-{task_id}.md",
    }
    if owns is not None:
        task["file_scope"] = {"owns": owns}
    return task


# ---------------------------------------------------------------------------
# Test: detect API task type
# ---------------------------------------------------------------------------

class TestDetectApiTask:
    """Tasks with routes/, endpoints/, or api/ in file_scope should be 'api'."""

    def test_detect_routes(self):
        task = _make_task("1.1", owns=["routes/users.py", "routes/auth.py"])
        result = detect_task_type(task)
        assert result == "api", f"Expected 'api' for routes/ files, got '{result}'"

    def test_detect_endpoints(self):
        task = _make_task("1.2", owns=["endpoints/health.py"])
        result = detect_task_type(task)
        assert result == "api", f"Expected 'api' for endpoints/ files, got '{result}'"

    def test_detect_api_dir(self):
        task = _make_task("1.3", owns=["api/v1/users.py"])
        result = detect_task_type(task)
        assert result == "api", f"Expected 'api' for api/ files, got '{result}'"


# ---------------------------------------------------------------------------
# Test: detect test task type
# ---------------------------------------------------------------------------

class TestDetectTestTask:
    """Tasks with tests/ or test_ in file_scope should be 'test'."""

    def test_detect_tests_dir(self):
        task = _make_task("2.1", owns=["tests/test_auth.py", "tests/test_db.py"])
        result = detect_task_type(task)
        assert result == "test", f"Expected 'test' for tests/ files, got '{result}'"

    def test_detect_test_prefix(self):
        task = _make_task("2.2", owns=["test_utils.py"])
        result = detect_task_type(task)
        assert result == "test", f"Expected 'test' for test_ files, got '{result}'"


# ---------------------------------------------------------------------------
# Test: detect script task type
# ---------------------------------------------------------------------------

class TestDetectScriptTask:
    """Tasks with hooks/ or bin/ in file_scope should be 'script'."""

    def test_detect_hooks(self):
        task = _make_task("3.1", owns=["hooks/pre-commit.sh", "hooks/post-push.sh"])
        result = detect_task_type(task)
        assert result == "script", f"Expected 'script' for hooks/ files, got '{result}'"

    def test_detect_bin(self):
        task = _make_task("3.2", owns=["bin/run.sh"])
        result = detect_task_type(task)
        assert result == "script", f"Expected 'script' for bin/ files, got '{result}'"


# ---------------------------------------------------------------------------
# Test: unknown patterns default to 'general'
# ---------------------------------------------------------------------------

class TestDetectUnknown:
    """Tasks with unrecognized file patterns should default to 'general'."""

    def test_unrecognized_pattern(self):
        task = _make_task("4.1", owns=["random/stuff.txt", "docs/readme.md"])
        result = detect_task_type(task)
        assert result == "general", (
            f"Expected 'general' for unrecognized patterns, got '{result}'"
        )

    def test_no_file_scope(self):
        task = _make_task("4.2")  # no file_scope at all
        result = detect_task_type(task)
        assert result == "general", (
            f"Expected 'general' when no file_scope, got '{result}'"
        )

    def test_empty_owns(self):
        task = _make_task("4.3", owns=[])
        result = detect_task_type(task)
        assert result == "general", (
            f"Expected 'general' when owns is empty, got '{result}'"
        )


# ---------------------------------------------------------------------------
# Test: guidance varies by type
# ---------------------------------------------------------------------------

class TestGuidanceVaries:
    """Different task types should produce different guidance text."""

    def test_guidance_varies(self):
        types = ["api", "ui", "data", "infra", "test", "script", "general"]
        guidances = set()
        for t in types:
            guidance = get_agent_guidance(t)
            guidances.add(guidance)
        # All 7 types must produce distinct guidance
        assert len(guidances) == len(types), (
            f"Expected {len(types)} distinct guidances, got {len(guidances)}. "
            "Some task types returned identical guidance."
        )


# ---------------------------------------------------------------------------
# Test: guidance is never empty
# ---------------------------------------------------------------------------

class TestGuidanceNotEmpty:
    """All task types must return non-empty guidance strings."""

    def test_guidance_not_empty(self):
        types = ["api", "ui", "data", "infra", "test", "script", "general"]
        for t in types:
            guidance = get_agent_guidance(t)
            assert isinstance(guidance, str), (
                f"Guidance for '{t}' must be a string, got {type(guidance).__name__}"
            )
            assert len(guidance.strip()) > 0, (
                f"Guidance for '{t}' must not be empty"
            )


# ---------------------------------------------------------------------------
# Test: CLI usage
# ---------------------------------------------------------------------------

class TestCLI:
    """CLI: python3 task_router.py plan.yaml TASK_ID should output JSON."""

    def test_cli_output(self, tmp_path):
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
                            "name": "API Task",
                            "status": "pending",
                            "depends_on": [],
                            "file_scope": {
                                "owns": ["routes/users.py", "routes/auth.py"],
                            },
                            "deliverables": {"backend": "b", "frontend": "f"},
                            "tests": {
                                "quantitative": {"command": "echo pass"},
                                "qualitative": {"criteria": ["ok"]},
                            },
                            "prompt_file": "tasks/task-1.1.md",
                        },
                    ],
                },
            ],
        }
        plan_path = tmp_path / "plan.yaml"
        with open(plan_path, "w") as f:
            yaml.dump(plan, f, default_flow_style=False)

        script_path = os.path.join(
            os.path.dirname(__file__), "../../scripts/task_router.py"
        )
        result = subprocess.run(
            [sys.executable, script_path, str(plan_path), "1.1"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"CLI exited with code {result.returncode}: {result.stderr}"
        )

        output = json.loads(result.stdout.strip())
        assert "task_type" in output, "CLI output missing 'task_type' key"
        assert "guidance" in output, "CLI output missing 'guidance' key"
        assert output["task_type"] == "api", (
            f"Expected task_type 'api', got '{output['task_type']}'"
        )
        assert len(output["guidance"]) > 0, "CLI guidance must not be empty"
