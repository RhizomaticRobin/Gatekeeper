import os
import sys
import yaml
import pytest

# Allow importing from scripts/
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts')
sys.path.insert(0, os.path.abspath(SCRIPTS_DIR))


def _minimal_plan():
    """Return a minimal valid plan dict with 2 phases and 4 tasks."""
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
                        "status": "completed",
                        "depends_on": [],
                        "deliverables": {"backend": "impl A", "frontend": "ui A"},
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
                        "deliverables": {"backend": "impl B", "frontend": "ui B"},
                        "tests": {
                            "quantitative": {"command": "echo pass"},
                            "qualitative": {"criteria": ["works"]},
                        },
                        "prompt_file": "tasks/task-1.2.md",
                    },
                ],
            },
            {
                "id": 2,
                "name": "Phase 2",
                "tasks": [
                    {
                        "id": "2.1",
                        "name": "Task C",
                        "status": "pending",
                        "depends_on": ["1.2"],
                        "deliverables": {"backend": "impl C", "frontend": "ui C"},
                        "tests": {
                            "quantitative": {"command": "echo pass"},
                            "qualitative": {"criteria": ["works"]},
                        },
                        "prompt_file": "tasks/task-2.1.md",
                    },
                    {
                        "id": "2.2",
                        "name": "Task D",
                        "status": "pending",
                        "depends_on": ["1.2"],
                        "deliverables": {"backend": "impl D", "frontend": "ui D"},
                        "tests": {
                            "quantitative": {"command": "echo pass"},
                            "qualitative": {"criteria": ["works"]},
                        },
                        "prompt_file": "tasks/task-2.2.md",
                    },
                ],
            },
        ],
    }


@pytest.fixture
def sample_plan():
    """Return a minimal valid plan dict."""
    return _minimal_plan()


@pytest.fixture
def plan_file(tmp_path):
    """Write a sample plan YAML to a temp file and return the path."""
    plan = _minimal_plan()
    path = tmp_path / "plan.yaml"
    with open(path, "w") as f:
        yaml.dump(plan, f, default_flow_style=False)
    return str(path)


@pytest.fixture
def empty_plan():
    """Return a plan dict with no tasks."""
    return {
        "metadata": {
            "project": "empty-project",
            "dev_server_command": "echo ok",
            "dev_server_url": "http://localhost:3000",
            "model_profile": "default",
        },
        "phases": [],
    }
