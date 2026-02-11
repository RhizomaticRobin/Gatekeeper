"""Tests for file locking in scripts/plan_utils.py.

Validates:
  - save_plan creates a lock file
  - save_plan uses atomic writes (tempfile + os.replace)
  - update_task_status holds lock across read-modify-write
  - Concurrent writers don't corrupt the plan
  - Lock file path is plan.yaml.lock
"""

import os
import sys
import threading
import time
import tempfile

import pytest
import yaml

# Allow importing from scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from plan_utils import (
    load_plan,
    save_plan,
    update_task_status,
    _plan_lock,
)


def _make_plan(num_tasks=4):
    """Return a plan dict with the given number of tasks across 2 phases."""
    tasks_phase1 = []
    tasks_phase2 = []
    for i in range(1, num_tasks + 1):
        task = {
            "id": f"1.{i}",
            "name": f"Task {i}",
            "status": "pending",
            "depends_on": [],
            "deliverables": {"backend": "test"},
            "tests": {"quantitative": {"command": "echo pass"}},
            "prompt_file": f"tasks/task-1.{i}.md",
        }
        if i <= num_tasks // 2:
            tasks_phase1.append(task)
        else:
            task["id"] = f"2.{i - num_tasks // 2}"
            task["name"] = f"Task P2-{i - num_tasks // 2}"
            task["prompt_file"] = f"tasks/task-2.{i - num_tasks // 2}.md"
            tasks_phase2.append(task)
    return {
        "metadata": {
            "project": "lock-test",
            "dev_server_command": "echo ok",
            "dev_server_url": "http://localhost:3000",
            "model_profile": "default",
        },
        "phases": [
            {"id": 1, "name": "Phase 1", "tasks": tasks_phase1},
            {"id": 2, "name": "Phase 2", "tasks": tasks_phase2},
        ],
    }


def _write_plan_file(path, plan):
    """Write plan to path directly (without locking) for test setup."""
    with open(path, "w") as f:
        yaml.dump(plan, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


class TestSavePlanCreatesLockFile:
    """save_plan should create a .lock file alongside the plan file."""

    def test_save_plan_creates_lock_file(self, tmp_path):
        plan_path = str(tmp_path / "plan.yaml")
        lock_path = plan_path + ".lock"
        plan = _make_plan(4)

        save_plan(plan_path, plan)

        assert os.path.exists(lock_path), (
            f"Expected lock file at {lock_path} but it does not exist"
        )


class TestSavePlanAtomicWrite:
    """save_plan should use tempfile + os.replace so partial writes don't corrupt."""

    def test_save_plan_atomic_write(self, tmp_path):
        """Original file should not be corrupted if we can verify atomic pattern.
        Write a plan, then write again. The file should always be valid YAML."""
        plan_path = str(tmp_path / "plan.yaml")
        plan = _make_plan(4)

        # First write
        save_plan(plan_path, plan)
        loaded1 = load_plan(plan_path)
        assert loaded1["metadata"]["project"] == "lock-test"

        # Second write with modification
        plan["metadata"]["project"] = "lock-test-updated"
        save_plan(plan_path, plan)
        loaded2 = load_plan(plan_path)
        assert loaded2["metadata"]["project"] == "lock-test-updated"

        # Verify file is valid YAML (not partially written)
        with open(plan_path, "r") as f:
            content = f.read()
        parsed = yaml.safe_load(content)
        assert parsed is not None
        assert "phases" in parsed

    def test_save_plan_does_not_write_directly_to_target(self, tmp_path, monkeypatch):
        """Verify save_plan writes to a temp file first, then replaces.
        We do this by checking that os.replace is called (via monkeypatch)."""
        plan_path = str(tmp_path / "plan.yaml")
        plan = _make_plan(4)

        replace_calls = []
        original_replace = os.replace

        def tracked_replace(src, dst):
            replace_calls.append((src, dst))
            return original_replace(src, dst)

        monkeypatch.setattr("os.replace", tracked_replace)

        save_plan(plan_path, plan)

        assert len(replace_calls) >= 1, "os.replace should have been called"
        # The destination should be the plan path
        assert replace_calls[0][1] == plan_path
        # The source should be a temp file (not the plan path itself)
        assert replace_calls[0][0] != plan_path


class TestUpdateTaskStatusLocked:
    """update_task_status should hold the lock across the entire read-modify-write."""

    def test_update_task_status_locked(self, tmp_path):
        """Two sequential updates should not corrupt the file."""
        plan_path = str(tmp_path / "plan.yaml")
        plan = _make_plan(4)
        _write_plan_file(plan_path, plan)

        result1 = update_task_status(plan_path, "1.1", "completed")
        assert result1 is True

        result2 = update_task_status(plan_path, "1.2", "completed")
        assert result2 is True

        # Both updates should be present
        final_plan = load_plan(plan_path)
        for phase in final_plan["phases"]:
            for task in phase["tasks"]:
                if task["id"] in ("1.1", "1.2"):
                    assert task["status"] == "completed", (
                        f"Task {task['id']} should be completed but is {task['status']}"
                    )


class TestConcurrentWriters:
    """10 threads each updating different tasks should all succeed without corruption."""

    def test_concurrent_writers(self, tmp_path):
        # Create a plan with 10 tasks
        plan = {
            "metadata": {
                "project": "concurrent-test",
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
                            "id": f"1.{i}",
                            "name": f"Task {i}",
                            "status": "pending",
                            "depends_on": [],
                            "deliverables": {"backend": "test"},
                            "tests": {"quantitative": {"command": "echo pass"}},
                            "prompt_file": f"tasks/task-1.{i}.md",
                        }
                        for i in range(1, 11)
                    ],
                }
            ],
        }
        plan_path = str(tmp_path / "plan.yaml")
        _write_plan_file(plan_path, plan)

        errors = []
        results = {}

        def update_worker(task_id):
            try:
                ok = update_task_status(plan_path, task_id, "completed")
                results[task_id] = ok
            except Exception as e:
                errors.append((task_id, str(e)))

        threads = []
        for i in range(1, 11):
            t = threading.Thread(target=update_worker, args=(f"1.{i}",))
            threads.append(t)

        # Start all threads
        for t in threads:
            t.start()

        # Wait for all threads
        for t in threads:
            t.join(timeout=30)

        # No errors
        assert errors == [], f"Errors during concurrent writes: {errors}"

        # All tasks should be completed
        final_plan = load_plan(plan_path)
        for task in final_plan["phases"][0]["tasks"]:
            assert task["status"] == "completed", (
                f"Task {task['id']} should be completed but is {task['status']}"
            )

        # All results should be True
        for task_id, ok in results.items():
            assert ok is True, f"update_task_status returned False for {task_id}"


class TestLockFilePath:
    """Lock file should be at plan.yaml.lock."""

    def test_lock_file_path(self, tmp_path):
        plan_path = str(tmp_path / "plan.yaml")
        lock_path = plan_path + ".lock"
        plan = _make_plan(4)

        save_plan(plan_path, plan)

        assert os.path.exists(lock_path)
        # Verify the lock file name specifically
        assert lock_path.endswith(".yaml.lock")

    def test_plan_lock_context_manager_uses_correct_path(self, tmp_path):
        """The _plan_lock context manager should use plan_path + '.lock'."""
        plan_path = str(tmp_path / "myplan.yaml")
        expected_lock = plan_path + ".lock"

        # Use _plan_lock directly
        with _plan_lock(plan_path):
            assert os.path.exists(expected_lock), (
                f"Lock file {expected_lock} should exist while lock is held"
            )
