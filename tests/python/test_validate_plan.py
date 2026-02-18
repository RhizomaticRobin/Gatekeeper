"""Tests for scripts/validate-plan.py

Every validation rule in validate-plan.py has at least one test.
Import via importlib because the filename has a hyphen.
"""

import os
import sys
import importlib.util

import yaml
import pytest

# Import validate-plan.py via importlib (hyphenated filename)
_spec = importlib.util.spec_from_file_location(
    "validate_plan",
    os.path.join(os.path.dirname(__file__), "../../scripts/validate-plan.py"),
)
validate_plan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate_plan)
validate = validate_plan.validate


def write_plan(tmp_path, plan_dict):
    """Write a plan dict as YAML to tmp_path and return the file path."""
    path = tmp_path / "plan.yaml"
    with open(path, "w") as f:
        yaml.dump(plan_dict, f, default_flow_style=False)
    return str(path)


def _valid_plan():
    """Return a fully valid plan dict with all required fields."""
    return {
        "metadata": {
            "project": "test-project",
            "dev_server_command": "echo ok",
            "dev_server_url": "http://localhost:3000",
            "model_profile": "default",
            "test_framework": "pytest",
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
                        "deliverables": {
                            "backend": "backend impl",
                            "frontend": "frontend impl",
                        },
                        "tests": {
                            "quantitative": {"command": "echo pass"},
                            "qualitative": {"criteria": ["it works"]},
                        },
                        "prompt_file": "tasks/task-1.1.md",
                    },
                ],
            },
        ],
    }


def _valid_plan_two_tasks():
    """Return a valid plan with two tasks for dependency testing."""
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
                "tasks": [
                    {
                        "id": "1.1",
                        "name": "Task A",
                        "status": "pending",
                        "depends_on": [],
                        "deliverables": {
                            "backend": "backend A",
                            "frontend": "frontend A",
                        },
                        "tests": {
                            "quantitative": {"command": "echo pass"},
                            "qualitative": {"criteria": ["works"]},
                        },
                        "prompt_file": "tasks/task-1.1.md",
                    },
                    {
                        "id": "1.2",
                        "name": "Task B",
                        "status": "pending",
                        "depends_on": ["1.1"],
                        "deliverables": {
                            "backend": "backend B",
                            "frontend": "frontend B",
                        },
                        "tests": {
                            "quantitative": {"command": "echo pass"},
                            "qualitative": {"criteria": ["works"]},
                        },
                        "prompt_file": "tasks/task-1.2.md",
                    },
                ],
            },
        ],
    }


# ===========================================================================
# Valid plans
# ===========================================================================


class TestValidPlans:
    def test_validate_valid_plan(self, tmp_path, capsys):
        """Full valid plan returns exit code 0 with PASSED message."""
        plan = _valid_plan()
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 0
        assert "PASSED" in captured.out

    def test_validate_minimal_plan(self, tmp_path, capsys):
        """Minimal valid plan with only required fields returns 0."""
        plan = {
            "metadata": {
                "project": "minimal",
                "dev_server_command": "echo ok",
                "dev_server_url": "http://localhost:3000",
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
                            "deliverables": {
                                "backend": "impl",
                                "frontend": "ui",
                            },
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
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 0
        assert "PASSED" in captured.out

    def test_validate_valid_plan_two_tasks(self, tmp_path, capsys):
        """Valid plan with two tasks and dependency returns 0."""
        plan = _valid_plan_two_tasks()
        path = write_plan(tmp_path, plan)
        result = validate(path)
        assert result == 0


# ===========================================================================
# Metadata validation
# ===========================================================================


class TestMetadataValidation:
    def test_validate_missing_project(self, tmp_path, capsys):
        """Missing metadata.project produces an error."""
        plan = _valid_plan()
        del plan["metadata"]["project"]
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "metadata.project" in captured.err

    def test_validate_missing_dev_server_command(self, tmp_path, capsys):
        """Missing metadata.dev_server_command produces an error."""
        plan = _valid_plan()
        del plan["metadata"]["dev_server_command"]
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "metadata.dev_server_command" in captured.err

    def test_validate_missing_dev_server_url(self, tmp_path, capsys):
        """Missing metadata.dev_server_url produces an error."""
        plan = _valid_plan()
        del plan["metadata"]["dev_server_url"]
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "metadata.dev_server_url" in captured.err

    def test_validate_metadata_not_mapping(self, tmp_path, capsys):
        """metadata that is not a mapping produces an error."""
        plan = _valid_plan()
        plan["metadata"] = "not a mapping"
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "metadata must be a mapping" in captured.err


# ===========================================================================
# Phase validation
# ===========================================================================


class TestPhaseValidation:
    def test_validate_no_phases(self, tmp_path, capsys):
        """Empty phases list produces an error."""
        plan = _valid_plan()
        plan["phases"] = []
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "phases must be a non-empty list" in captured.err

    def test_validate_phase_missing_id(self, tmp_path, capsys):
        """Phase without id produces an error."""
        plan = _valid_plan()
        del plan["phases"][0]["id"]
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "must have an 'id' field" in captured.err

    def test_validate_phase_missing_name(self, tmp_path, capsys):
        """Phase without name produces an error."""
        plan = _valid_plan()
        del plan["phases"][0]["name"]
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "must have a 'name' field" in captured.err


# ===========================================================================
# Task field validation
# ===========================================================================


class TestTaskFieldValidation:
    def test_validate_missing_task_id(self, tmp_path, capsys):
        """Task without id produces an error."""
        plan = _valid_plan()
        del plan["phases"][0]["tasks"][0]["id"]
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "missing required field 'id'" in captured.err

    def test_validate_missing_task_name(self, tmp_path, capsys):
        """Task without name produces an error."""
        plan = _valid_plan()
        del plan["phases"][0]["tasks"][0]["name"]
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "missing required field 'name'" in captured.err

    def test_validate_missing_status(self, tmp_path, capsys):
        """Task without status produces an error."""
        plan = _valid_plan()
        del plan["phases"][0]["tasks"][0]["status"]
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "missing required field 'status'" in captured.err

    def test_validate_invalid_status(self, tmp_path, capsys):
        """Task with invalid status enum produces an error."""
        plan = _valid_plan()
        plan["phases"][0]["tasks"][0]["status"] = "invalid_status"
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "invalid status" in captured.err

    def test_validate_missing_depends_on(self, tmp_path, capsys):
        """Task without depends_on produces an error."""
        plan = _valid_plan()
        del plan["phases"][0]["tasks"][0]["depends_on"]
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "missing required field 'depends_on'" in captured.err

    def test_validate_depends_on_not_list(self, tmp_path, capsys):
        """depends_on that is not a list produces an error."""
        plan = _valid_plan()
        plan["phases"][0]["tasks"][0]["depends_on"] = "not-a-list"
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "depends_on must be a list" in captured.err


# ===========================================================================
# Deliverables validation
# ===========================================================================


class TestDeliverablesValidation:
    def test_validate_missing_backend(self, tmp_path, capsys):
        """Missing deliverables.backend produces an error."""
        plan = _valid_plan()
        del plan["phases"][0]["tasks"][0]["deliverables"]["backend"]
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "deliverables.backend is required" in captured.err

    def test_validate_missing_frontend(self, tmp_path, capsys):
        """Missing deliverables.frontend produces a warning (not error)."""
        plan = _valid_plan()
        del plan["phases"][0]["tasks"][0]["deliverables"]["frontend"]
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 0
        assert "deliverables.frontend" in captured.err  # warning present


# ===========================================================================
# Tests validation
# ===========================================================================


class TestTestsValidation:
    def test_validate_missing_test_command(self, tmp_path, capsys):
        """Missing tests.quantitative.command produces an error."""
        plan = _valid_plan()
        del plan["phases"][0]["tasks"][0]["tests"]["quantitative"]["command"]
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "tests.quantitative.command is required" in captured.err

    def test_validate_missing_qualitative_criteria(self, tmp_path, capsys):
        """Empty qualitative criteria list produces an error."""
        plan = _valid_plan()
        plan["phases"][0]["tasks"][0]["tests"]["qualitative"]["criteria"] = []
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "tests.qualitative.criteria is required" in captured.err


# ===========================================================================
# Prompt file validation
# ===========================================================================


class TestPromptFileValidation:
    def test_validate_missing_prompt_file(self, tmp_path, capsys):
        """Missing prompt_file produces an error."""
        plan = _valid_plan()
        del plan["phases"][0]["tasks"][0]["prompt_file"]
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "prompt_file is required" in captured.err


# ===========================================================================
# Dependency validation
# ===========================================================================


class TestDependencyValidation:
    def test_validate_unknown_dependency(self, tmp_path, capsys):
        """depends_on referencing a nonexistent task produces an error."""
        plan = _valid_plan()
        plan["phases"][0]["tasks"][0]["depends_on"] = ["99.99"]
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "unknown task" in captured.err

    def test_validate_duplicate_task_id(self, tmp_path, capsys):
        """Duplicate task IDs produce an error."""
        plan = _valid_plan()
        # Add a second task with the same ID
        duplicate_task = {
            "id": "1.1",
            "name": "Duplicate Task",
            "status": "pending",
            "depends_on": [],
            "deliverables": {"backend": "impl", "frontend": "ui"},
            "tests": {
                "quantitative": {"command": "echo pass"},
                "qualitative": {"criteria": ["ok"]},
            },
            "prompt_file": "tasks/task-dup.md",
        }
        plan["phases"][0]["tasks"].append(duplicate_task)
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "Duplicate task ID" in captured.err

    def test_validate_dependency_cycle(self, tmp_path, capsys):
        """Circular dependencies produce an error."""
        plan = {
            "metadata": {
                "project": "cycle-test",
                "dev_server_command": "echo ok",
                "dev_server_url": "http://localhost:3000",
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
                            "depends_on": ["1.2"],
                            "deliverables": {
                                "backend": "impl A",
                                "frontend": "ui A",
                            },
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
                            "depends_on": ["1.1"],
                            "deliverables": {
                                "backend": "impl B",
                                "frontend": "ui B",
                            },
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
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "cycle" in captured.err.lower() or "cycle" in captured.out.lower()


# ===========================================================================
# must_haves validation
# ===========================================================================


class TestMustHavesValidation:
    def test_validate_must_haves_not_mapping(self, tmp_path, capsys):
        """must_haves that is not a mapping produces an error."""
        plan = _valid_plan()
        plan["phases"][0]["tasks"][0]["must_haves"] = "not a mapping"
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "must_haves must be a mapping" in captured.err

    def test_validate_must_haves_truths_not_list(self, tmp_path, capsys):
        """must_haves.truths that is not a list produces an error."""
        plan = _valid_plan()
        plan["phases"][0]["tasks"][0]["must_haves"] = {
            "truths": "not a list",
        }
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "must_haves.truths must be a list" in captured.err

    def test_validate_must_haves_artifacts_not_list(self, tmp_path, capsys):
        """must_haves.artifacts that is not a list produces an error."""
        plan = _valid_plan()
        plan["phases"][0]["tasks"][0]["must_haves"] = {
            "artifacts": "not a list",
        }
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "must_haves.artifacts must be a list" in captured.err

    def test_validate_must_haves_key_links_not_list(self, tmp_path, capsys):
        """must_haves.key_links that is not a list produces an error."""
        plan = _valid_plan()
        plan["phases"][0]["tasks"][0]["must_haves"] = {
            "key_links": "not a list",
        }
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "must_haves.key_links must be a list" in captured.err

    def test_validate_phase_must_haves_not_mapping(self, tmp_path, capsys):
        """Phase-level must_haves that is not a mapping produces an error."""
        plan = _valid_plan()
        plan["phases"][0]["must_haves"] = "not a mapping"
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "must_haves must be a mapping" in captured.err

    def test_validate_phase_must_haves_truths_not_list(self, tmp_path, capsys):
        """Phase-level must_haves.truths that is not a list produces an error."""
        plan = _valid_plan()
        plan["phases"][0]["must_haves"] = {
            "truths": "not a list",
        }
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "must_haves.truths must be a list" in captured.err

    def test_validate_valid_must_haves(self, tmp_path, capsys):
        """Valid must_haves on a task does not produce errors."""
        plan = _valid_plan()
        plan["phases"][0]["tasks"][0]["must_haves"] = {
            "truths": ["it works"],
            "artifacts": ["file.py"],
            "key_links": ["source: lib.py"],
        }
        path = write_plan(tmp_path, plan)
        result = validate(path)
        assert result == 0


# ===========================================================================
# Wave validation
# ===========================================================================


class TestWaveValidation:
    def test_validate_wave_not_integer(self, tmp_path, capsys):
        """Non-integer wave produces an error."""
        plan = _valid_plan()
        plan["phases"][0]["tasks"][0]["wave"] = "two"
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "wave must be a positive integer" in captured.err

    def test_validate_wave_zero(self, tmp_path, capsys):
        """Wave of 0 produces an error (must be >= 1)."""
        plan = _valid_plan()
        plan["phases"][0]["tasks"][0]["wave"] = 0
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "wave must be a positive integer" in captured.err

    def test_validate_wave_negative(self, tmp_path, capsys):
        """Negative wave produces an error."""
        plan = _valid_plan()
        plan["phases"][0]["tasks"][0]["wave"] = -1
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "wave must be a positive integer" in captured.err

    def test_validate_wave_valid(self, tmp_path, capsys):
        """Valid wave (positive integer) does not produce errors."""
        plan = _valid_plan()
        plan["phases"][0]["tasks"][0]["wave"] = 1
        path = write_plan(tmp_path, plan)
        result = validate(path)
        assert result == 0


# ===========================================================================
# file_scope validation
# ===========================================================================


class TestFileScopeValidation:
    def test_validate_file_scope_not_mapping(self, tmp_path, capsys):
        """file_scope that is not a mapping produces an error."""
        plan = _valid_plan()
        plan["phases"][0]["tasks"][0]["file_scope"] = "not a mapping"
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "file_scope must be a mapping" in captured.err

    def test_validate_file_scope_owns_not_list(self, tmp_path, capsys):
        """file_scope.owns that is not a list of strings produces an error."""
        plan = _valid_plan()
        plan["phases"][0]["tasks"][0]["file_scope"] = {
            "owns": "not a list",
        }
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "file_scope.owns must be a list of strings" in captured.err

    def test_validate_file_scope_reads_not_list(self, tmp_path, capsys):
        """file_scope.reads that is not a list of strings produces an error."""
        plan = _valid_plan()
        plan["phases"][0]["tasks"][0]["file_scope"] = {
            "reads": 123,
        }
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "file_scope.reads must be a list of strings" in captured.err

    def test_validate_file_scope_overlap_warning(self, tmp_path, capsys):
        """Overlapping file_scope.owns between independent tasks produces a warning."""
        plan = _valid_plan_two_tasks()
        # Make the tasks independent (no dependency between them)
        plan["phases"][0]["tasks"][1]["depends_on"] = []
        # Give them overlapping file_scope.owns
        plan["phases"][0]["tasks"][0]["file_scope"] = {
            "owns": ["src/shared/"],
        }
        plan["phases"][0]["tasks"][1]["file_scope"] = {
            "owns": ["src/shared/utils.py"],
        }
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        # Overlap warning goes to stderr but does NOT cause validation failure
        assert "Warning" in captured.err
        assert "overlapping file_scope.owns" in captured.err.lower() or "overlapping" in captured.err.lower()

    def test_validate_file_scope_no_overlap_when_dependent(self, tmp_path, capsys):
        """No overlap warning when tasks have a dependency relationship."""
        plan = _valid_plan_two_tasks()
        # Tasks are dependent (1.2 depends on 1.1)
        plan["phases"][0]["tasks"][0]["file_scope"] = {
            "owns": ["src/shared/"],
        }
        plan["phases"][0]["tasks"][1]["file_scope"] = {
            "owns": ["src/shared/utils.py"],
        }
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 0
        # No overlap warning because they have a dependency relationship
        assert "overlapping" not in captured.err.lower()

    def test_validate_file_scope_valid(self, tmp_path, capsys):
        """Valid file_scope does not produce errors."""
        plan = _valid_plan()
        plan["phases"][0]["tasks"][0]["file_scope"] = {
            "owns": ["src/main.py", "src/utils.py"],
            "reads": ["config.yaml"],
        }
        path = write_plan(tmp_path, plan)
        result = validate(path)
        assert result == 0


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    def test_validate_root_not_mapping(self, tmp_path, capsys):
        """Plan root that is not a mapping produces an error."""
        path = tmp_path / "plan.yaml"
        with open(path, "w") as f:
            f.write("just a string\n")
        result = validate(str(path))
        captured = capsys.readouterr()
        assert result == 1
        assert "root must be a mapping" in captured.err

    def test_validate_phases_not_list(self, tmp_path, capsys):
        """Phases that is not a list produces an error."""
        plan = _valid_plan()
        plan["phases"] = "not a list"
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "phases must be a non-empty list" in captured.err

    def test_validate_qualitative_not_mapping(self, tmp_path, capsys):
        """tests.qualitative that is not a mapping produces an error."""
        plan = _valid_plan()
        plan["phases"][0]["tasks"][0]["tests"]["qualitative"] = "not a mapping"
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "tests.qualitative must be a mapping" in captured.err

    def test_validate_deliverables_not_mapping(self, tmp_path, capsys):
        """deliverables that is not a mapping produces an error."""
        plan = _valid_plan()
        plan["phases"][0]["tasks"][0]["deliverables"] = "not a mapping"
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "deliverables must be a mapping" in captured.err

    def test_validate_tests_not_mapping(self, tmp_path, capsys):
        """tests that is not a mapping produces an error."""
        plan = _valid_plan()
        plan["phases"][0]["tasks"][0]["tests"] = "not a mapping"
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "tests must be a mapping" in captured.err

    def test_validate_multiple_errors(self, tmp_path, capsys):
        """Plan with multiple errors reports all of them."""
        plan = _valid_plan()
        task = plan["phases"][0]["tasks"][0]
        del task["name"]
        del task["prompt_file"]
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        # Should report multiple errors
        assert captured.err.count("Error:") >= 2

    def test_validate_completed_status(self, tmp_path, capsys):
        """Task with 'completed' status is valid."""
        plan = _valid_plan()
        plan["phases"][0]["tasks"][0]["status"] = "completed"
        path = write_plan(tmp_path, plan)
        result = validate(path)
        assert result == 0

    def test_validate_in_progress_status(self, tmp_path, capsys):
        """Task with 'in_progress' status is valid."""
        plan = _valid_plan()
        plan["phases"][0]["tasks"][0]["status"] = "in_progress"
        path = write_plan(tmp_path, plan)
        result = validate(path)
        assert result == 0


# ===========================================================================
# Resilience metadata validation
# ===========================================================================


class TestResilienceMetadata:
    def test_resilience_metadata_accepted(self, tmp_path, capsys):
        """Plan with all 4 resilience fields in metadata passes validation."""
        plan = _valid_plan()
        plan["metadata"]["max_gatekeeper_iterations"] = 50
        plan["metadata"]["timeout_hours"] = 8
        plan["metadata"]["stuck_threshold"] = 3
        plan["metadata"]["circuit_breaker_threshold"] = 5
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 0
        assert "PASSED" in captured.out

    def test_resilience_metadata_partial(self, tmp_path, capsys):
        """Plan with only some resilience fields passes (they're optional)."""
        plan = _valid_plan()
        plan["metadata"]["max_gatekeeper_iterations"] = 100
        plan["metadata"]["timeout_hours"] = 12
        # stuck_threshold and circuit_breaker_threshold omitted
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 0
        assert "PASSED" in captured.out

    def test_resilience_metadata_bad_types(self, tmp_path, capsys):
        """Non-integer resilience fields produce errors."""
        plan = _valid_plan()
        plan["metadata"]["max_gatekeeper_iterations"] = "not_a_number"
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "max_gatekeeper_iterations" in captured.err

    def test_resilience_metadata_negative_value(self, tmp_path, capsys):
        """Negative resilience field values produce errors."""
        plan = _valid_plan()
        plan["metadata"]["timeout_hours"] = -1
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "timeout_hours" in captured.err

    def test_resilience_metadata_zero_value(self, tmp_path, capsys):
        """Zero resilience field values produce errors (must be positive)."""
        plan = _valid_plan()
        plan["metadata"]["stuck_threshold"] = 0
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "stuck_threshold" in captured.err


# ===========================================================================
# Project context validation
# ===========================================================================


class TestProjectContext:
    def test_project_context_accepted(self, tmp_path, capsys):
        """Plan with project_context dict in metadata passes validation."""
        plan = _valid_plan()
        plan["metadata"]["project_context"] = {
            "vision": "Build a CLI tool",
            "users": "developers",
            "tech_stack": ["python", "bash"],
        }
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 0
        assert "PASSED" in captured.out

    def test_project_context_bad_type(self, tmp_path, capsys):
        """project_context as string produces error."""
        plan = _valid_plan()
        plan["metadata"]["project_context"] = "not a dict"
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 1
        assert "project_context" in captured.err

    def test_project_context_in_metadata(self, tmp_path, capsys):
        """Plan with full discovery project_context (all fields) passes validation.

        This verifies that validate-plan.py accepts metadata.project_context
        containing all discovery fields from the deep discovery interview:
        vision, primary_user, problem, success_criteria, core_features,
        out_of_scope, future_features, greenfield, tech_constraints,
        integrations, deploy_target, quality_preference.
        """
        plan = _valid_plan()
        plan["metadata"]["project_context"] = {
            "vision": "A task management app for remote teams",
            "primary_user": "Remote team leads and project managers",
            "problem": "Distributed teams lack visibility into task progress",
            "success_criteria": "Teams can track tasks in real-time across timezones",
            "core_features": [
                "Task board with drag-and-drop",
                "Real-time sync across clients",
                "Team member assignments",
                "Due date tracking",
                "Activity feed",
            ],
            "out_of_scope": [
                "Video conferencing",
                "File storage",
                "Invoicing",
            ],
            "future_features": [
                "Gantt chart view",
                "Time tracking integration",
            ],
            "greenfield": True,
            "tech_constraints": "Must use TypeScript and PostgreSQL",
            "integrations": ["Slack API", "GitHub webhooks"],
            "deploy_target": "AWS ECS with RDS",
            "quality_preference": "quality",
        }
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 0
        assert "PASSED" in captured.out


# ===========================================================================
# Frontend optional validation
# ===========================================================================


class TestFrontendOptional:
    def test_frontend_optional(self, tmp_path, capsys):
        """Plan task without deliverables.frontend passes (warning only)."""
        plan = _valid_plan()
        del plan["phases"][0]["tasks"][0]["deliverables"]["frontend"]
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 0
        # Should produce a warning, not an error
        assert "Warning" in captured.err or "warning" in captured.err.lower()

    def test_frontend_present_still_works(self, tmp_path, capsys):
        """Plan with deliverables.frontend still passes."""
        plan = _valid_plan()
        # frontend is already present in _valid_plan()
        path = write_plan(tmp_path, plan)
        result = validate(path)
        captured = capsys.readouterr()
        assert result == 0
        assert "PASSED" in captured.out


# ===========================================================================
# Existing plans backward compatibility
# ===========================================================================


class TestBackwardCompatibility:
    def test_existing_plans_still_valid(self, tmp_path, capsys):
        """All existing fixture plans still pass validation."""
        fixtures_dir = os.path.join(
            os.path.dirname(__file__), "..", "fixtures"
        )
        plans = []
        for root, dirs, files in os.walk(fixtures_dir):
            for f in files:
                if f == "plan.yaml":
                    plans.append(os.path.join(root, f))
        assert len(plans) > 0, "No fixture plans found"
        for plan_path in plans:
            result = validate(plan_path)
            assert result == 0, f"Fixture plan failed validation: {plan_path}"
