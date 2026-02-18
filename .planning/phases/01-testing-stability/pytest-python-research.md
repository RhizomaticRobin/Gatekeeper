# Research: pytest for Python Unit Testing

**Phase:** 01 -- Testing & Stability
**Requirements:** R-001 (test plan_utils.py), R-002 (test validate-plan.py)
**Date:** 2026-02-11
**Status:** Complete

---

## 1. Overview

This document covers pytest best practices for testing the two Python scripts central to Gatekeeper's plan orchestration:

- **`/home/user/gatekeeper/scripts/plan_utils.py`** -- Shared utilities: YAML loading/saving, task lookup, dependency resolution, topological sort, CLI via argparse.
- **`/home/user/gatekeeper/scripts/validate-plan.py`** -- Validates a plan.yaml file structure, checks for required fields, invalid statuses, broken dependency references, and dependency cycles. CLI entry point uses raw `sys.argv`.

Both scripts are file-I/O heavy (reading/writing YAML), produce JSON output to stdout/stderr, and use `sys.exit()` for error signaling. pytest provides purpose-built fixtures for all of these patterns.

### What Needs Testing

| Module | Functions / Entry Points | Testing Challenge |
|--------|--------------------------|-------------------|
| `plan_utils.py` | `load_plan`, `save_plan`, `find_task`, `update_task_status`, `get_next_task`, `get_all_unblocked_tasks`, `get_all_task_ids`, `topological_sort`, `get_task_must_haves`, `get_phase_must_haves`, `get_task_wave`, `get_model_profile`, `task_to_json`, `main()` | File I/O (YAML read/write), argparse CLI, JSON stdout |
| `validate-plan.py` | `validate(path)`, `main()` | File I/O, stderr/stdout output, `sys.exit` codes, complex validation logic |

---

## 2. Recommended Project Structure

The project currently has no tests directory, no `conftest.py`, no `pyproject.toml`, and no `pytest.ini`. pytest is not yet installed. Here is the recommended structure:

```
gatekeeper/
  scripts/
    plan_utils.py
    validate-plan.py
    ...
  tests/
    __init__.py              # (empty, makes tests a package)
    conftest.py              # shared fixtures: sample plans, tmp YAML files
    test_plan_utils.py       # tests for plan_utils functions + CLI
    test_validate_plan.py    # tests for validate-plan.py functions + CLI
  pyproject.toml             # (or pytest.ini) -- pytest configuration
```

### Why This Layout

- **Separate `tests/` directory at project root**: Keeps test code isolated from production scripts. pytest auto-discovers files matching `test_*.py`.
- **`conftest.py` in `tests/`**: Fixtures defined here are automatically available to all test files in the directory without needing imports. This is the right place for the shared sample plan data and YAML file creation helpers.
- **`__init__.py` in `tests/`**: Allows test files to import from `scripts/` using relative paths or `sys.path` manipulation.
- **`pyproject.toml` at project root**: Central place to configure pytest options, test paths, and Python tool settings.

### Minimal `pyproject.toml` Configuration

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["scripts"]
# pythonpath tells pytest to add scripts/ to sys.path so imports work
```

The `pythonpath` setting is critical. It means test files can simply write `from plan_utils import load_plan` without needing `sys.path` hacks. Available in pytest 7.0+.

### Import Consideration for `validate-plan.py`

The filename `validate-plan.py` contains a hyphen, which is not a valid Python identifier. This means you cannot import it with a normal `import` statement. Two options:

1. **Use `importlib`** in the test file:
   ```python
   import importlib.util
   spec = importlib.util.spec_from_file_location("validate_plan", "/path/to/validate-plan.py")
   validate_plan = importlib.util.module_from_spec(spec)
   spec.loader.exec_module(validate_plan)
   ```

2. **Preferred: Test via `subprocess`** for the CLI entry point, and test the `validate()` function by importing it from a conftest fixture that loads the module dynamically.

---

## 3. Key pytest Fixtures

### 3.1 `tmp_path` -- Temporary File I/O

**What it does:** Provides a unique `pathlib.Path` temporary directory per test function. Automatically cleaned up after the test session.

**Why it matters:** Both scripts read/write YAML files. Tests must create real files on disk without polluting the working directory or interfering with other tests.

**Usage pattern for our scripts:**

```python
import yaml

def test_load_plan(tmp_path):
    # Create a minimal plan YAML file in the temp directory
    plan_data = {
        "metadata": {"project": "test", "dev_server_command": "npm run dev", "dev_server_url": "http://localhost:3000"},
        "phases": [
            {
                "id": "phase-1",
                "name": "Phase 1",
                "tasks": [
                    {
                        "id": "T-001",
                        "name": "Task 1",
                        "status": "pending",
                        "depends_on": [],
                        "deliverables": {"backend": "file.py", "frontend": "file.tsx"},
                        "tests": {
                            "quantitative": {"command": "pytest"},
                            "qualitative": {"criteria": ["works"]}
                        },
                        "prompt_file": "prompt.md"
                    }
                ]
            }
        ]
    }
    plan_file = tmp_path / "plan.yaml"
    plan_file.write_text(yaml.dump(plan_data), encoding="utf-8")

    from plan_utils import load_plan
    result = load_plan(str(plan_file))  # load_plan expects str path, not Path
    assert result["metadata"]["project"] == "test"
    assert len(result["phases"]) == 1
```

**Key detail:** `load_plan()` uses `open(path, "r")` with a string path, so pass `str(plan_file)` not the `Path` object directly (though modern Python handles both, explicit is safer).

**`tmp_path_factory`** -- Session-scoped variant. Use when you need the same temp directory across multiple tests (e.g., an expensive plan fixture):

```python
@pytest.fixture(scope="session")
def shared_plan_file(tmp_path_factory):
    fn = tmp_path_factory.mktemp("plans") / "plan.yaml"
    fn.write_text(yaml.dump(SAMPLE_PLAN), encoding="utf-8")
    return fn
```

### 3.2 `capsys` -- Capturing stdout/stderr

**What it does:** Captures text written to `sys.stdout` and `sys.stderr`. Returns a named tuple with `.out` and `.err` attributes via `capsys.readouterr()`.

**Why it matters:** Both scripts produce JSON output to stdout and error messages to stderr. The `validate` function prints to both streams.

**Usage pattern:**

```python
import json
import pytest

def test_validate_passes(capsys, tmp_path):
    plan_file = tmp_path / "plan.yaml"
    plan_file.write_text(yaml.dump(VALID_PLAN))

    from validate_plan_module import validate
    exit_code = validate(str(plan_file))

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Validation PASSED" in captured.out
    assert captured.err == "" or "Warning" in captured.err  # warnings OK

def test_validate_fails_missing_metadata(capsys, tmp_path):
    bad_plan = {"metadata": {}, "phases": [{"id": "p1", "name": "P", "tasks": []}]}
    plan_file = tmp_path / "bad.yaml"
    plan_file.write_text(yaml.dump(bad_plan))

    exit_code = validate(str(plan_file))

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "metadata.project is required" in captured.err
```

**Important:** Call `capsys.readouterr()` after the function under test completes. Each call resets the buffer, so do not call it before unless you want to clear previous output.

### 3.3 `monkeypatch` -- Mocking sys.argv, Environment, Attributes

**What it does:** Safely modifies attributes, dict items, environment variables, or `sys.path` for the duration of a single test. Automatically reverted after the test.

**Why it matters:** Both `main()` functions read `sys.argv`. `validate-plan.py` uses `os.path.isfile()`. We need to control these without affecting other tests.

**Usage pattern for sys.argv:**

```python
def test_main_next_task(monkeypatch, capsys, tmp_path):
    plan_file = tmp_path / "plan.yaml"
    plan_file.write_text(yaml.dump(SAMPLE_PLAN))

    monkeypatch.setattr("sys.argv", ["plan_utils.py", str(plan_file), "--next-task"])

    from plan_utils import main
    main()

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["id"] == "T-001"
```

**Usage pattern for sys.exit:**

```python
def test_validate_main_no_args(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["validate-plan.py"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Usage:" in captured.err
```

---

## 4. Example Test Patterns for plan_utils.py Functions

### 4.1 Fixture: Reusable Plan Data in conftest.py

```python
# tests/conftest.py
import pytest
import yaml

MINIMAL_PLAN = {
    "metadata": {
        "project": "TestProject",
        "dev_server_command": "npm start",
        "dev_server_url": "http://localhost:3000",
        "model_profile": "default",
        "test_framework": "pytest"
    },
    "phases": [
        {
            "id": "phase-1",
            "name": "Phase 1",
            "tasks": [
                {
                    "id": "T-001",
                    "name": "First Task",
                    "status": "completed",
                    "depends_on": [],
                    "deliverables": {"backend": "api.py", "frontend": "App.tsx"},
                    "tests": {
                        "quantitative": {"command": "pytest tests/"},
                        "qualitative": {"criteria": ["UI renders correctly"]}
                    },
                    "prompt_file": "prompts/001.md"
                },
                {
                    "id": "T-002",
                    "name": "Second Task",
                    "status": "pending",
                    "depends_on": ["T-001"],
                    "deliverables": {"backend": "models.py", "frontend": "Form.tsx"},
                    "tests": {
                        "quantitative": {"command": "pytest tests/"},
                        "qualitative": {"criteria": ["Form submits"]}
                    },
                    "prompt_file": "prompts/002.md"
                },
                {
                    "id": "T-003",
                    "name": "Third Task",
                    "status": "pending",
                    "depends_on": ["T-001"],
                    "deliverables": {"backend": "auth.py", "frontend": "Login.tsx"},
                    "tests": {
                        "quantitative": {"command": "pytest tests/"},
                        "qualitative": {"criteria": ["Login works"]}
                    },
                    "prompt_file": "prompts/003.md"
                }
            ]
        }
    ]
}


@pytest.fixture
def sample_plan():
    """Return a copy of the minimal plan dict (no file I/O)."""
    import copy
    return copy.deepcopy(MINIMAL_PLAN)


@pytest.fixture
def plan_file(tmp_path, sample_plan):
    """Write sample plan to a temp YAML file and return its path as a string."""
    path = tmp_path / "plan.yaml"
    path.write_text(yaml.dump(sample_plan, default_flow_style=False), encoding="utf-8")
    return str(path)
```

### 4.2 Testing Pure Functions (No File I/O)

These functions accept a plan dict, so they need no file I/O at all:

```python
# tests/test_plan_utils.py
from plan_utils import (
    find_task, get_all_task_ids, get_next_task, get_all_unblocked_tasks,
    topological_sort, get_task_must_haves, get_phase_must_haves,
    get_task_wave, get_model_profile, task_to_json
)


class TestFindTask:
    def test_finds_existing_task(self, sample_plan):
        phase, task = find_task(sample_plan, "T-001")
        assert task is not None
        assert task["id"] == "T-001"
        assert phase["id"] == "phase-1"

    def test_returns_none_for_missing(self, sample_plan):
        phase, task = find_task(sample_plan, "NONEXISTENT")
        assert phase is None
        assert task is None

    def test_finds_task_with_int_id(self, sample_plan):
        """IDs are coerced to str internally."""
        # Modify plan to have numeric ID
        sample_plan["phases"][0]["tasks"][0]["id"] = 1
        phase, task = find_task(sample_plan, 1)
        assert task is not None

    def test_finds_task_with_string_id_matching_int(self, sample_plan):
        sample_plan["phases"][0]["tasks"][0]["id"] = 1
        phase, task = find_task(sample_plan, "1")
        assert task is not None


class TestGetAllTaskIds:
    def test_returns_all_ids(self, sample_plan):
        ids = get_all_task_ids(sample_plan)
        assert ids == ["T-001", "T-002", "T-003"]

    def test_empty_plan(self):
        assert get_all_task_ids({"phases": []}) == []

    def test_missing_phases_key(self):
        assert get_all_task_ids({}) == []


class TestGetNextTask:
    def test_returns_first_unblocked_pending(self, sample_plan):
        # T-001 is completed, T-002 and T-003 depend on T-001 -> both unblocked
        # get_next_task returns the first one found
        task = get_next_task(sample_plan)
        assert task is not None
        assert task["id"] in ("T-002", "T-003")

    def test_returns_none_when_all_completed(self, sample_plan):
        for phase in sample_plan["phases"]:
            for task in phase["tasks"]:
                task["status"] = "completed"
        assert get_next_task(sample_plan) is None

    def test_returns_none_when_blocked(self, sample_plan):
        # Make T-001 pending again -- now T-002 and T-003 are blocked
        sample_plan["phases"][0]["tasks"][0]["status"] = "pending"
        # T-001 has no deps, so it should be returned
        task = get_next_task(sample_plan)
        assert task["id"] == "T-001"

    def test_skips_in_progress_tasks(self, sample_plan):
        sample_plan["phases"][0]["tasks"][1]["status"] = "in_progress"
        task = get_next_task(sample_plan)
        # T-002 is in_progress (skipped), T-003 is pending and unblocked
        assert task["id"] == "T-003"


class TestGetAllUnblockedTasks:
    def test_returns_all_unblocked(self, sample_plan):
        tasks = get_all_unblocked_tasks(sample_plan)
        ids = [t["id"] for t in tasks]
        assert "T-002" in ids
        assert "T-003" in ids

    def test_returns_empty_when_all_blocked(self):
        plan = {
            "phases": [{
                "id": "p1", "name": "P1",
                "tasks": [
                    {"id": "A", "status": "pending", "depends_on": ["B"]},
                    {"id": "B", "status": "pending", "depends_on": ["A"]}
                ]
            }]
        }
        assert get_all_unblocked_tasks(plan) == []


class TestTopologicalSort:
    def test_no_cycle(self, sample_plan):
        sorted_ids, has_cycle = topological_sort(sample_plan)
        assert has_cycle is False
        assert "T-001" in sorted_ids
        # T-001 must come before T-002 and T-003
        assert sorted_ids.index("T-001") < sorted_ids.index("T-002")
        assert sorted_ids.index("T-001") < sorted_ids.index("T-003")

    def test_detects_cycle(self):
        cyclic_plan = {
            "phases": [{
                "id": "p1", "name": "P1",
                "tasks": [
                    {"id": "A", "status": "pending", "depends_on": ["B"]},
                    {"id": "B", "status": "pending", "depends_on": ["A"]}
                ]
            }]
        }
        _, has_cycle = topological_sort(cyclic_plan)
        assert has_cycle is True

    def test_empty_plan(self):
        sorted_ids, has_cycle = topological_sort({"phases": []})
        assert sorted_ids == []
        assert has_cycle is False


class TestTaskToJson:
    def test_converts_task_dict(self):
        task = {
            "id": "T-001", "name": "Test", "status": "pending",
            "depends_on": [1, 2], "deliverables": {"backend": "x"},
            "tests": {"quantitative": {"command": "pytest"}},
            "prompt_file": "p.md", "must_haves": {}, "file_scope": {}, "wave": 1
        }
        result = task_to_json(task)
        assert result["id"] == "T-001"
        assert result["depends_on"] == ["1", "2"]  # coerced to str
        assert result["wave"] == 1

    def test_none_input(self):
        assert task_to_json(None) is None

    def test_missing_optional_fields(self):
        task = {"id": "X", "name": "Minimal"}
        result = task_to_json(task)
        assert result["status"] == "pending"  # default
        assert result["depends_on"] == []
        assert result["wave"] is None
```

### 4.3 Testing File I/O Functions

```python
class TestLoadPlan:
    def test_loads_valid_yaml(self, plan_file):
        from plan_utils import load_plan
        plan = load_plan(plan_file)
        assert plan["metadata"]["project"] == "TestProject"

    def test_raises_on_missing_file(self):
        from plan_utils import load_plan
        with pytest.raises(FileNotFoundError):
            load_plan("/nonexistent/path/plan.yaml")

    def test_raises_on_invalid_yaml(self, tmp_path):
        from plan_utils import load_plan
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("{{{{invalid yaml: [", encoding="utf-8")
        with pytest.raises(Exception):  # yaml.YAMLError
            load_plan(str(bad_file))


class TestSavePlan:
    def test_roundtrip(self, tmp_path, sample_plan):
        from plan_utils import load_plan, save_plan
        path = str(tmp_path / "out.yaml")
        save_plan(path, sample_plan)
        reloaded = load_plan(path)
        assert reloaded["metadata"]["project"] == "TestProject"
        assert len(reloaded["phases"][0]["tasks"]) == 3


class TestUpdateTaskStatus:
    def test_updates_and_saves(self, plan_file):
        from plan_utils import update_task_status, load_plan
        result = update_task_status(plan_file, "T-002", "completed")
        assert result is True
        # Verify persistence
        plan = load_plan(plan_file)
        _, task = find_task(plan, "T-002")
        assert task["status"] == "completed"

    def test_returns_false_for_missing_task(self, plan_file):
        from plan_utils import update_task_status
        result = update_task_status(plan_file, "NONEXISTENT", "completed")
        assert result is False
```

### 4.4 Testing the CLI (`main()`) via argparse

The `plan_utils.main()` function uses `argparse.parse_args()` which reads from `sys.argv`. Two strategies:

**Strategy A: monkeypatch sys.argv (recommended for plan_utils.py)**

```python
import json

class TestPlanUtilsCLI:
    def test_next_task(self, monkeypatch, capsys, plan_file):
        monkeypatch.setattr("sys.argv", ["plan_utils.py", plan_file, "--next-task"])
        from plan_utils import main
        main()
        output = json.loads(capsys.readouterr().out)
        assert output["id"] in ("T-002", "T-003")

    def test_all_ids(self, monkeypatch, capsys, plan_file):
        monkeypatch.setattr("sys.argv", ["plan_utils.py", plan_file, "--all-ids"])
        from plan_utils import main
        main()
        output = json.loads(capsys.readouterr().out)
        assert output == ["T-001", "T-002", "T-003"]

    def test_find_task(self, monkeypatch, capsys, plan_file):
        monkeypatch.setattr("sys.argv", ["plan_utils.py", plan_file, "--find-task", "T-001"])
        from plan_utils import main
        main()
        output = json.loads(capsys.readouterr().out)
        assert output["id"] == "T-001"

    def test_complete_task(self, monkeypatch, capsys, plan_file):
        monkeypatch.setattr("sys.argv", ["plan_utils.py", plan_file, "--complete-task", "T-002"])
        from plan_utils import main
        main()
        output = json.loads(capsys.readouterr().out)
        assert output["status"] == "completed"

    def test_complete_nonexistent_task(self, monkeypatch, capsys, plan_file):
        monkeypatch.setattr("sys.argv", ["plan_utils.py", plan_file, "--complete-task", "NOPE"])
        from plan_utils import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err
```

**Strategy B: Subprocess (for true end-to-end CLI testing)**

```python
import subprocess

def test_cli_end_to_end(plan_file):
    result = subprocess.run(
        ["python3", "scripts/plan_utils.py", plan_file, "--all-ids"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    ids = json.loads(result.stdout)
    assert "T-001" in ids
```

Subprocess testing is heavier but tests the actual script execution including shebang, imports, and `if __name__ == "__main__"` guard.

---

## 5. Testing validate-plan.py

### 5.1 Importing the Hyphenated Module

Since `validate-plan.py` has a hyphen in its name, use importlib in conftest.py:

```python
# tests/conftest.py (add to existing)
import importlib.util
import os

@pytest.fixture
def validate_module():
    """Import validate-plan.py despite the hyphenated filename."""
    spec = importlib.util.spec_from_file_location(
        "validate_plan",
        os.path.join(os.path.dirname(__file__), "..", "scripts", "validate-plan.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
```

### 5.2 Testing the `validate()` Function

The `validate()` function is well-designed for testing: it takes a file path, returns an integer exit code (0 or 1), and prints to stdout/stderr. No `sys.exit()` call -- that is only in `main()`.

```python
# tests/test_validate_plan.py

class TestValidateFunction:
    def test_valid_plan_passes(self, validate_module, capsys, plan_file):
        exit_code = validate_module.validate(plan_file)
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "Validation PASSED" in captured.out

    def test_missing_metadata_project(self, validate_module, capsys, tmp_path):
        plan = {
            "metadata": {"dev_server_command": "x", "dev_server_url": "y"},
            "phases": [{"id": "p1", "name": "P", "tasks": []}]
        }
        path = tmp_path / "bad.yaml"
        path.write_text(yaml.dump(plan))
        exit_code = validate_module.validate(str(path))
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "metadata.project is required" in captured.err

    def test_duplicate_task_ids(self, validate_module, capsys, tmp_path):
        plan = {
            "metadata": {"project": "x", "dev_server_command": "x", "dev_server_url": "y"},
            "phases": [{
                "id": "p1", "name": "P",
                "tasks": [
                    {"id": "T-001", "name": "A", "status": "pending", "depends_on": [],
                     "deliverables": {"backend": "x", "frontend": "y"},
                     "tests": {"quantitative": {"command": "c"}, "qualitative": {"criteria": ["x"]}},
                     "prompt_file": "p.md"},
                    {"id": "T-001", "name": "B", "status": "pending", "depends_on": [],
                     "deliverables": {"backend": "x", "frontend": "y"},
                     "tests": {"quantitative": {"command": "c"}, "qualitative": {"criteria": ["x"]}},
                     "prompt_file": "p.md"}
                ]
            }]
        }
        path = tmp_path / "dup.yaml"
        path.write_text(yaml.dump(plan))
        exit_code = validate_module.validate(str(path))
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "Duplicate task ID" in captured.err

    def test_invalid_status(self, validate_module, capsys, tmp_path):
        plan = make_plan_with_task({"status": "unknown"})
        path = tmp_path / "bad_status.yaml"
        path.write_text(yaml.dump(plan))
        exit_code = validate_module.validate(str(path))
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "invalid status" in captured.err

    def test_dependency_cycle_detected(self, validate_module, capsys, tmp_path):
        plan = {
            "metadata": {"project": "x", "dev_server_command": "x", "dev_server_url": "y"},
            "phases": [{
                "id": "p1", "name": "P",
                "tasks": [
                    make_full_task("A", depends_on=["B"]),
                    make_full_task("B", depends_on=["A"])
                ]
            }]
        }
        path = tmp_path / "cycle.yaml"
        path.write_text(yaml.dump(plan))
        exit_code = validate_module.validate(str(path))
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "cycle" in captured.err.lower()

    def test_broken_dependency_reference(self, validate_module, capsys, tmp_path):
        plan = {
            "metadata": {"project": "x", "dev_server_command": "x", "dev_server_url": "y"},
            "phases": [{
                "id": "p1", "name": "P",
                "tasks": [
                    make_full_task("A", depends_on=["NONEXISTENT"])
                ]
            }]
        }
        path = tmp_path / "broken.yaml"
        path.write_text(yaml.dump(plan))
        exit_code = validate_module.validate(str(path))
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "unknown task" in captured.err.lower()
```

### 5.3 Testing validate-plan.py `main()` (sys.exit + sys.argv)

```python
class TestValidateMain:
    def test_no_args_exits_1(self, validate_module, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["validate-plan.py"])
        with pytest.raises(SystemExit) as exc_info:
            validate_module.main()
        assert exc_info.value.code == 1

    def test_missing_file_exits_1(self, validate_module, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["validate-plan.py", "/no/such/file.yaml"])
        with pytest.raises(SystemExit) as exc_info:
            validate_module.main()
        assert exc_info.value.code == 1
        assert "file not found" in capsys.readouterr().err

    def test_valid_file_exits_0(self, validate_module, monkeypatch, capsys, plan_file):
        monkeypatch.setattr("sys.argv", ["validate-plan.py", plan_file])
        with pytest.raises(SystemExit) as exc_info:
            validate_module.main()
        assert exc_info.value.code == 0
```

---

## 6. conftest.py Helper Functions

To reduce boilerplate in validation tests, define helpers:

```python
# tests/conftest.py (helpers section)

def make_full_task(task_id, depends_on=None, status="pending", **overrides):
    """Create a fully valid task dict for testing."""
    task = {
        "id": task_id,
        "name": f"Task {task_id}",
        "status": status,
        "depends_on": depends_on or [],
        "deliverables": {"backend": "file.py", "frontend": "file.tsx"},
        "tests": {
            "quantitative": {"command": "pytest"},
            "qualitative": {"criteria": ["it works"]}
        },
        "prompt_file": f"prompts/{task_id}.md"
    }
    task.update(overrides)
    return task


def make_plan_with_task(task_overrides):
    """Create a minimal valid plan with one task, applying overrides to the task."""
    task = make_full_task("T-001")
    task.update(task_overrides)
    return {
        "metadata": {"project": "test", "dev_server_command": "x", "dev_server_url": "y"},
        "phases": [{"id": "p1", "name": "Phase 1", "tasks": [task]}]
    }
```

---

## 7. Gotchas and Pitfalls

### 7.1 Do Not Patch `builtins.open` Globally

The pytest documentation explicitly warns against patching `builtins.open` because it can break pytest internals (test collection, plugin loading, etc.). Instead:
- Use `tmp_path` to create real temporary files (preferred).
- If you must mock, use `monkeypatch.context()` to limit the scope.

### 7.2 `sys.argv` Persistence Across Tests

If you use `monkeypatch.setattr("sys.argv", [...])`, monkeypatch restores the original value after the test. However, if you forget monkeypatch and directly assign `sys.argv = [...]`, it bleeds into other tests. Always use monkeypatch.

### 7.3 argparse Caches

`argparse.ArgumentParser` is created inside `main()` in plan_utils.py, so there is no caching issue. But if the parser were module-level, repeated calls in the same process could cause problems. The current code is safe.

### 7.4 `SystemExit` vs Return Codes

- `validate()` **returns** an integer (0 or 1) -- test with `assert exit_code == 0`.
- `main()` calls `sys.exit()` -- test with `pytest.raises(SystemExit)`.
- `plan_utils.main()` calls `sys.exit(1)` only on the error path for `--complete-task` with a bad ID. Other paths just print and return normally.

### 7.5 Hyphenated Filename Import

`validate-plan.py` cannot be imported with `import validate-plan` (syntax error). Use `importlib.util.spec_from_file_location` as shown in section 5.1. Consider whether to rename the file to `validate_plan.py` for simplicity.

### 7.6 YAML Serialization Differences

PyYAML's `dump()` may produce slightly different formatting than hand-written YAML. Tests should compare parsed data structures, not raw YAML strings. For example:

```python
# Bad: fragile string comparison
assert plan_file.read_text() == expected_yaml_string

# Good: compare parsed structures
assert yaml.safe_load(plan_file.read_text()) == expected_dict
```

### 7.7 `sys.path` Manipulation in validate-plan.py

Line 14 of validate-plan.py does `sys.path.insert(0, os.path.dirname(...))`. This is fine for production but means the module modifies `sys.path` as a side effect when imported. The `pythonpath` setting in `pyproject.toml` makes this unnecessary for tests, but the side effect is harmless.

### 7.8 `copy.deepcopy` for Fixture Data

The `sample_plan` fixture must return a deep copy of the plan dict. If tests mutate the plan (e.g., changing task statuses), a shared reference would cause test pollution. Always use `copy.deepcopy()`.

### 7.9 Test Isolation for `update_task_status`

`update_task_status` reads and writes the file. Each test that calls it should use its own `plan_file` fixture instance (which `tmp_path` guarantees since it is function-scoped).

### 7.10 Order of capsys.readouterr() and pytest.raises

When combining `capsys` with `pytest.raises(SystemExit)`, call `capsys.readouterr()` **after** the `with` block exits:

```python
# Correct
with pytest.raises(SystemExit):
    main()
captured = capsys.readouterr()  # after the with block

# Incorrect -- captures nothing useful
captured = capsys.readouterr()  # too early
with pytest.raises(SystemExit):
    main()
```

---

## 8. Installation and Running

```bash
# Install pytest and PyYAML
pip install pytest pyyaml

# Run all tests
pytest tests/ -v

# Run with coverage
pip install pytest-cov
pytest tests/ --cov=scripts --cov-report=term-missing

# Run a specific test class
pytest tests/test_plan_utils.py::TestFindTask -v

# Run a specific test
pytest tests/test_plan_utils.py::TestFindTask::test_finds_existing_task -v
```

---

## 9. Sources

- [pytest: How to use temporary directories and files in tests](https://docs.pytest.org/en/stable/how-to/tmp_path.html)
- [pytest: How to monkeypatch/mock modules and environments](https://docs.pytest.org/en/stable/how-to/monkeypatch.html)
- [pytest: How to capture stdout/stderr output](https://docs.pytest.org/en/stable/how-to/capture-stdout-stderr.html)
- [pytest: Good Integration Practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
- [Writing pytest tests against tools written with argparse (Simon Willison)](https://til.simonwillison.net/pytest/pytest-argparse)
- [Testing argparse Applications (PythonTest)](https://pythontest.com/testing-argparse-apps/)
- [5 Best Practices for Organizing Tests (Pytest with Eric)](https://pytest-with-eric.com/pytest-best-practices/pytest-organize-tests/)
- [How To Manage Temporary Files with Pytest tmp_path (Pytest with Eric)](https://pytest-with-eric.com/pytest-best-practices/pytest-tmp-path/)
- [Testing Argparse Applications - the Better Way (Jurgen Gmach)](https://jugmac00.github.io/blog/testing-argparse-applications-the-better-way/)
