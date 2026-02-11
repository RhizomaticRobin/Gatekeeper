"""Tests for scripts/plan_utils.py — all 13 public functions.

Organized in two waves:
  Wave 1 (T1): Pure functions — no filesystem needed
  Wave 2 (T2): I/O functions — uses tmp_path
"""

import sys
import os
import json
import pytest
import yaml

# Allow importing from scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from plan_utils import (
    load_plan,
    save_plan,
    find_task,
    update_task_status,
    get_next_task,
    get_all_unblocked_tasks,
    get_all_task_ids,
    topological_sort,
    get_task_must_haves,
    get_phase_must_haves,
    get_task_wave,
    get_model_profile,
    task_to_json,
)


# ============================================================
# Wave 1 (T1): Pure functions — no filesystem needed
# ============================================================


class TestFindTask:
    """Tests for find_task(plan, task_id)."""

    def test_find_existing_task(self, sample_plan):
        phase, task = find_task(sample_plan, "1.1")
        assert task is not None
        assert task["id"] == "1.1"
        assert task["name"] == "Task A"
        assert phase["id"] == 1

    def test_find_task_not_found(self, sample_plan):
        phase, task = find_task(sample_plan, "99.99")
        assert phase is None
        assert task is None

    def test_find_task_string_coercion(self, sample_plan):
        """Task IDs should be compared as strings even if passed as float."""
        phase, task = find_task(sample_plan, 1.1)
        assert task is not None
        assert str(task["id"]) == "1.1"

    def test_find_task_in_second_phase(self, sample_plan):
        phase, task = find_task(sample_plan, "2.1")
        assert task is not None
        assert task["name"] == "Task C"
        assert phase["id"] == 2


class TestGetAllTaskIds:
    """Tests for get_all_task_ids(plan)."""

    def test_normal_plan(self, sample_plan):
        ids = get_all_task_ids(sample_plan)
        assert ids == ["1.1", "1.2", "2.1", "2.2"]

    def test_empty_plan(self, empty_plan):
        ids = get_all_task_ids(empty_plan)
        assert ids == []

    def test_returns_strings(self, sample_plan):
        ids = get_all_task_ids(sample_plan)
        for tid in ids:
            assert isinstance(tid, str)


class TestGetNextTask:
    """Tests for get_next_task(plan)."""

    def test_simple_next(self, sample_plan):
        """1.1 is completed, 1.2 depends on 1.1 -> 1.2 is next."""
        task = get_next_task(sample_plan)
        assert task is not None
        assert task["id"] == "1.2"

    def test_with_deps_not_met(self, sample_plan):
        """If we set 1.1 to pending, nothing should be unblocked since
        1.2 depends on 1.1 and there is no task with no deps and pending status."""
        # Reset 1.1 to pending
        sample_plan["phases"][0]["tasks"][0]["status"] = "pending"
        # Now 1.1 has no deps and is pending, so it should be next
        task = get_next_task(sample_plan)
        assert task is not None
        assert task["id"] == "1.1"

    def test_all_completed(self, sample_plan):
        """When all tasks are completed, get_next_task returns None."""
        for phase in sample_plan["phases"]:
            for task in phase["tasks"]:
                task["status"] = "completed"
        result = get_next_task(sample_plan)
        assert result is None

    def test_empty_plan(self, empty_plan):
        result = get_next_task(empty_plan)
        assert result is None

    def test_skips_non_pending(self, sample_plan):
        """Tasks that are 'in_progress' should not be returned."""
        sample_plan["phases"][0]["tasks"][1]["status"] = "in_progress"
        task = get_next_task(sample_plan)
        # 1.2 is in_progress so skipped; 2.1 and 2.2 depend on 1.2 which is not completed
        assert task is None


class TestGetAllUnblockedTasks:
    """Tests for get_all_unblocked_tasks(plan)."""

    def test_multiple_unblocked(self, sample_plan):
        """Complete 1.2 so that 2.1 and 2.2 become unblocked."""
        sample_plan["phases"][0]["tasks"][1]["status"] = "completed"
        unblocked = get_all_unblocked_tasks(sample_plan)
        ids = [t["id"] for t in unblocked]
        assert "2.1" in ids
        assert "2.2" in ids

    def test_none_unblocked(self, sample_plan):
        """Reset 1.1 to pending and mark 1.2 as blocked => only 1.1 unblocked."""
        sample_plan["phases"][0]["tasks"][0]["status"] = "pending"
        unblocked = get_all_unblocked_tasks(sample_plan)
        ids = [t["id"] for t in unblocked]
        # 1.1 has no deps and is pending
        assert "1.1" in ids
        # 1.2 depends on 1.1 which is not completed
        assert "1.2" not in ids

    def test_empty_plan(self, empty_plan):
        unblocked = get_all_unblocked_tasks(empty_plan)
        assert unblocked == []


class TestTopologicalSort:
    """Tests for topological_sort(plan)."""

    def test_valid_dag(self, sample_plan):
        sorted_ids, has_cycle = topological_sort(sample_plan)
        assert has_cycle is False
        assert set(sorted_ids) == {"1.1", "1.2", "2.1", "2.2"}
        # 1.1 must come before 1.2
        assert sorted_ids.index("1.1") < sorted_ids.index("1.2")
        # 1.2 must come before 2.1 and 2.2
        assert sorted_ids.index("1.2") < sorted_ids.index("2.1")
        assert sorted_ids.index("1.2") < sorted_ids.index("2.2")

    def test_cycle_detection(self):
        """Create a plan with a cycle: A -> B -> A."""
        cyclic_plan = {
            "metadata": {},
            "phases": [
                {
                    "id": 1,
                    "tasks": [
                        {"id": "A", "depends_on": ["B"], "status": "pending"},
                        {"id": "B", "depends_on": ["A"], "status": "pending"},
                    ],
                }
            ],
        }
        sorted_ids, has_cycle = topological_sort(cyclic_plan)
        assert has_cycle is True

    def test_independent_tasks(self):
        """Tasks with no deps should all be sortable."""
        plan = {
            "metadata": {},
            "phases": [
                {
                    "id": 1,
                    "tasks": [
                        {"id": "X", "depends_on": [], "status": "pending"},
                        {"id": "Y", "depends_on": [], "status": "pending"},
                        {"id": "Z", "depends_on": [], "status": "pending"},
                    ],
                }
            ],
        }
        sorted_ids, has_cycle = topological_sort(plan)
        assert has_cycle is False
        assert set(sorted_ids) == {"X", "Y", "Z"}

    def test_empty_plan(self, empty_plan):
        sorted_ids, has_cycle = topological_sort(empty_plan)
        assert has_cycle is False
        assert sorted_ids == []


class TestGetTaskMustHaves:
    """Tests for get_task_must_haves(plan, task_id)."""

    def test_must_haves_exists(self):
        plan = {
            "metadata": {},
            "phases": [
                {
                    "id": 1,
                    "tasks": [
                        {
                            "id": "1.1",
                            "status": "pending",
                            "must_haves": {"truths": ["auth works"], "artifacts": ["auth.py"]},
                        }
                    ],
                }
            ],
        }
        mh = get_task_must_haves(plan, "1.1")
        assert mh["truths"] == ["auth works"]
        assert mh["artifacts"] == ["auth.py"]

    def test_must_haves_missing_key(self, sample_plan):
        """Tasks in sample_plan have no must_haves key -> returns empty dict."""
        mh = get_task_must_haves(sample_plan, "1.1")
        assert mh == {}

    def test_must_haves_task_not_found(self, sample_plan):
        mh = get_task_must_haves(sample_plan, "99.99")
        assert mh == {}


class TestGetPhaseMustHaves:
    """Tests for get_phase_must_haves(plan, phase_id)."""

    def test_phase_must_haves_exists(self):
        plan = {
            "metadata": {},
            "phases": [
                {
                    "id": 1,
                    "must_haves": {"truths": ["phase 1 done"]},
                    "tasks": [],
                }
            ],
        }
        mh = get_phase_must_haves(plan, "1")
        assert mh == {"truths": ["phase 1 done"]}

    def test_phase_must_haves_not_found(self, sample_plan):
        mh = get_phase_must_haves(sample_plan, "99")
        assert mh == {}

    def test_phase_must_haves_int_coercion(self):
        """Phase ID passed as int should still work."""
        plan = {
            "metadata": {},
            "phases": [
                {
                    "id": 1,
                    "must_haves": {"artifacts": ["file.py"]},
                    "tasks": [],
                }
            ],
        }
        mh = get_phase_must_haves(plan, 1)
        assert mh == {"artifacts": ["file.py"]}


class TestGetTaskWave:
    """Tests for get_task_wave(plan, task_id)."""

    def test_wave_assigned(self):
        plan = {
            "metadata": {},
            "phases": [
                {
                    "id": 1,
                    "tasks": [
                        {"id": "1.1", "status": "pending", "wave": 2},
                    ],
                }
            ],
        }
        wave = get_task_wave(plan, "1.1")
        assert wave == 2

    def test_wave_none(self, sample_plan):
        """sample_plan tasks have no wave key -> returns None."""
        wave = get_task_wave(sample_plan, "1.1")
        assert wave is None

    def test_wave_task_not_found(self, sample_plan):
        wave = get_task_wave(sample_plan, "99.99")
        assert wave is None


class TestGetModelProfile:
    """Tests for get_model_profile(plan)."""

    def test_model_profile_set(self, sample_plan):
        result = get_model_profile(sample_plan)
        assert result == "default"

    def test_model_profile_custom(self):
        plan = {
            "metadata": {"model_profile": "advanced"},
            "phases": [],
        }
        result = get_model_profile(plan)
        assert result == "advanced"

    def test_model_profile_missing_returns_default(self):
        plan = {"metadata": {}, "phases": []}
        result = get_model_profile(plan)
        assert result == "default"

    def test_model_profile_no_metadata(self):
        plan = {"phases": []}
        result = get_model_profile(plan)
        assert result == "default"


class TestTaskToJson:
    """Tests for task_to_json(task)."""

    def test_full_task(self, sample_plan):
        _, task = find_task(sample_plan, "1.1")
        result = task_to_json(task)
        assert result["id"] == "1.1"
        assert result["name"] == "Task A"
        assert result["status"] == "completed"
        assert result["depends_on"] == []
        assert result["prompt_file"] == "tasks/task-1.1.md"
        assert isinstance(result["deliverables"], dict)
        assert isinstance(result["tests"], dict)
        # Verify it is JSON-serializable
        json.dumps(result)

    def test_none_input(self):
        result = task_to_json(None)
        assert result is None

    def test_minimal_task(self):
        """Task with only 'id' key — all others use defaults."""
        task = {"id": "X"}
        result = task_to_json(task)
        assert result["id"] == "X"
        assert result["name"] == ""
        assert result["status"] == "pending"
        assert result["depends_on"] == []
        assert result["deliverables"] == {}
        assert result["tests"] == {}
        assert result["prompt_file"] == ""
        assert result["must_haves"] == {}
        assert result["file_scope"] == {}
        assert result["wave"] is None

    def test_depends_on_coerced_to_strings(self):
        """depends_on values should all be strings."""
        task = {"id": "1.1", "depends_on": [1.0, 2.0]}
        result = task_to_json(task)
        assert result["depends_on"] == ["1.0", "2.0"]


# ============================================================
# Wave 2 (T2): I/O functions — uses tmp_path / filesystem
# ============================================================


class TestLoadPlan:
    """Tests for load_plan(path)."""

    def test_load_valid_yaml(self, plan_file):
        plan = load_plan(plan_file)
        assert "metadata" in plan
        assert "phases" in plan
        assert len(plan["phases"]) == 2

    def test_load_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_plan(str(tmp_path / "nonexistent.yaml"))

    def test_load_invalid_yaml(self, tmp_path):
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("{{{{not valid yaml: [")
        with pytest.raises(Exception):
            load_plan(str(bad_file))


class TestSavePlan:
    """Tests for save_plan(path, plan)."""

    def test_roundtrip(self, tmp_path, sample_plan):
        path = str(tmp_path / "out.yaml")
        save_plan(path, sample_plan)
        loaded = load_plan(path)
        assert loaded["metadata"]["project"] == sample_plan["metadata"]["project"]
        assert len(loaded["phases"]) == len(sample_plan["phases"])

    def test_creates_file(self, tmp_path, sample_plan):
        path = str(tmp_path / "new_file.yaml")
        assert not os.path.exists(path)
        save_plan(path, sample_plan)
        assert os.path.exists(path)

    def test_roundtrip_preserves_task_ids(self, tmp_path, sample_plan):
        path = str(tmp_path / "rt.yaml")
        save_plan(path, sample_plan)
        loaded = load_plan(path)
        original_ids = get_all_task_ids(sample_plan)
        loaded_ids = get_all_task_ids(loaded)
        assert original_ids == loaded_ids


class TestUpdateTaskStatus:
    """Tests for update_task_status(path, task_id, status)."""

    def test_update_success(self, plan_file):
        result = update_task_status(plan_file, "1.2", "completed")
        assert result is True
        plan = load_plan(plan_file)
        _, task = find_task(plan, "1.2")
        assert task["status"] == "completed"

    def test_update_not_found(self, plan_file):
        result = update_task_status(plan_file, "99.99", "completed")
        assert result is False
