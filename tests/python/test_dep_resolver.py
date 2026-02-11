"""Tests for autonomous dependency resolution (scripts/dep_resolver.py).

Validates:
  - analyze_error detects missing npm packages from 'Cannot find module' errors
  - analyze_error detects missing Python packages from 'ModuleNotFoundError'
  - detect_missing_env finds undefined env var references
  - resolve generates safe resolution commands (npm install, pip install)
  - Resolution actions are safe (install only, never remove/uninstall)
  - Clean output with no issues returns empty list
"""

import json
import os
import subprocess
import sys

import pytest

# Allow importing from scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from dep_resolver import analyze_error, resolve, detect_missing_env


class TestDetectMissingNpm:
    """analyze_error should detect missing npm packages from Cannot find module errors."""

    def test_detect_single_npm_module(self):
        error_output = "Error: Cannot find module 'express'"
        issues = analyze_error(error_output)
        assert len(issues) >= 1
        npm_issues = [i for i in issues if i["type"] == "missing_npm"]
        assert len(npm_issues) == 1
        assert npm_issues[0]["package"] == "express"

    def test_detect_multiple_npm_modules(self):
        error_output = (
            "Error: Cannot find module 'lodash'\n"
            "Error: Cannot find module 'axios'\n"
        )
        issues = analyze_error(error_output)
        npm_issues = [i for i in issues if i["type"] == "missing_npm"]
        assert len(npm_issues) == 2
        packages = {i["package"] for i in npm_issues}
        assert packages == {"lodash", "axios"}

    def test_detect_scoped_npm_module(self):
        error_output = "Error: Cannot find module '@babel/core'"
        issues = analyze_error(error_output)
        npm_issues = [i for i in issues if i["type"] == "missing_npm"]
        assert len(npm_issues) == 1
        assert npm_issues[0]["package"] == "@babel/core"

    def test_detect_npm_relative_path_ignored(self):
        """Relative module paths like './foo' should NOT be flagged as missing npm packages."""
        error_output = "Error: Cannot find module './my-local-file'"
        issues = analyze_error(error_output)
        npm_issues = [i for i in issues if i["type"] == "missing_npm"]
        assert len(npm_issues) == 0


class TestDetectMissingPip:
    """analyze_error should detect missing Python packages from ModuleNotFoundError."""

    def test_detect_single_pip_module(self):
        error_output = "ModuleNotFoundError: No module named 'requests'"
        issues = analyze_error(error_output)
        pip_issues = [i for i in issues if i["type"] == "missing_pip"]
        assert len(pip_issues) == 1
        assert pip_issues[0]["package"] == "requests"

    def test_detect_multiple_pip_modules(self):
        error_output = (
            "ModuleNotFoundError: No module named 'flask'\n"
            "ModuleNotFoundError: No module named 'sqlalchemy'\n"
        )
        issues = analyze_error(error_output)
        pip_issues = [i for i in issues if i["type"] == "missing_pip"]
        assert len(pip_issues) == 2
        packages = {i["package"] for i in pip_issues}
        assert packages == {"flask", "sqlalchemy"}

    def test_detect_pip_submodule(self):
        """For 'No module named foo.bar', should extract top-level package 'foo'."""
        error_output = "ModuleNotFoundError: No module named 'yaml.loader'"
        issues = analyze_error(error_output)
        pip_issues = [i for i in issues if i["type"] == "missing_pip"]
        assert len(pip_issues) == 1
        assert pip_issues[0]["package"] == "yaml"


class TestDetectMissingEnv:
    """detect_missing_env should find undefined environment variable references."""

    def test_detect_process_env_undefined(self):
        error_output = "TypeError: Cannot read properties of undefined (reading 'split')\n  at process.env.DATABASE_URL is undefined"
        issues = detect_missing_env(error_output)
        assert len(issues) >= 1
        env_issues = [i for i in issues if i["type"] == "missing_env"]
        assert any(i["variable"] == "DATABASE_URL" for i in env_issues)

    def test_detect_multiple_env_vars(self):
        error_output = (
            "process.env.API_KEY is undefined\n"
            "process.env.SECRET_TOKEN is undefined\n"
        )
        issues = detect_missing_env(error_output)
        env_issues = [i for i in issues if i["type"] == "missing_env"]
        assert len(env_issues) == 2
        variables = {i["variable"] for i in env_issues}
        assert variables == {"API_KEY", "SECRET_TOKEN"}

    def test_no_env_issues(self):
        error_output = "Everything is fine, no env issues here."
        issues = detect_missing_env(error_output)
        env_issues = [i for i in issues if i["type"] == "missing_env"]
        assert len(env_issues) == 0


class TestResolveNpm:
    """resolve should generate npm install commands for missing npm packages."""

    def test_resolve_single_npm(self):
        issues = [{"type": "missing_npm", "package": "express"}]
        actions = resolve(issues)
        assert len(actions) >= 1
        npm_actions = [a for a in actions if a["action"] == "install"]
        assert len(npm_actions) == 1
        assert "npm install express" in npm_actions[0]["command"]

    def test_resolve_multiple_npm(self):
        issues = [
            {"type": "missing_npm", "package": "lodash"},
            {"type": "missing_npm", "package": "axios"},
        ]
        actions = resolve(issues)
        npm_actions = [a for a in actions if "npm install" in a["command"]]
        assert len(npm_actions) >= 1
        # All packages should appear in commands
        all_commands = " ".join(a["command"] for a in npm_actions)
        assert "lodash" in all_commands
        assert "axios" in all_commands


class TestResolvePip:
    """resolve should generate pip install commands for missing Python packages."""

    def test_resolve_single_pip(self):
        issues = [{"type": "missing_pip", "package": "requests"}]
        actions = resolve(issues)
        assert len(actions) >= 1
        pip_actions = [a for a in actions if a["action"] == "install"]
        assert len(pip_actions) == 1
        assert "pip install requests" in pip_actions[0]["command"]

    def test_resolve_multiple_pip(self):
        issues = [
            {"type": "missing_pip", "package": "flask"},
            {"type": "missing_pip", "package": "sqlalchemy"},
        ]
        actions = resolve(issues)
        pip_actions = [a for a in actions if "pip install" in a["command"]]
        assert len(pip_actions) >= 1
        all_commands = " ".join(a["command"] for a in pip_actions)
        assert "flask" in all_commands
        assert "sqlalchemy" in all_commands


class TestSafeResolution:
    """Resolution actions must be safe: only install, never remove or uninstall."""

    def test_no_remove_actions(self):
        issues = [
            {"type": "missing_npm", "package": "express"},
            {"type": "missing_pip", "package": "requests"},
        ]
        actions = resolve(issues)
        for action in actions:
            assert action["action"] == "install" or action["action"] == "prompt"
            assert "uninstall" not in action["command"].lower()
            assert "remove" not in action["command"].lower()

    def test_env_resolution_is_prompt(self):
        """Missing env vars should prompt the user, not auto-install anything."""
        issues = [{"type": "missing_env", "variable": "API_KEY"}]
        actions = resolve(issues)
        assert len(actions) >= 1
        assert all(a["action"] == "prompt" for a in actions)

    def test_mixed_issues_all_safe(self):
        issues = [
            {"type": "missing_npm", "package": "react"},
            {"type": "missing_pip", "package": "django"},
            {"type": "missing_env", "variable": "DB_HOST"},
        ]
        actions = resolve(issues)
        for action in actions:
            assert action["action"] in ("install", "prompt")
            cmd = action.get("command", "")
            assert "uninstall" not in cmd.lower()
            assert "remove" not in cmd.lower()


class TestNoIssues:
    """Clean output with no dependency issues should return empty list."""

    def test_clean_output_analyze(self):
        error_output = "All tests passed.\n3 passed in 1.23s"
        issues = analyze_error(error_output)
        assert issues == []

    def test_clean_output_env(self):
        error_output = "Server started on port 3000"
        issues = detect_missing_env(error_output)
        assert issues == []

    def test_empty_string_analyze(self):
        issues = analyze_error("")
        assert issues == []

    def test_empty_string_env(self):
        issues = detect_missing_env("")
        assert issues == []

    def test_resolve_empty_issues(self):
        actions = resolve([])
        assert actions == []


class TestCLI:
    """CLI interface for dep_resolver.py."""

    def _run_cli(self, *args):
        cmd = [sys.executable, os.path.join(
            os.path.dirname(__file__), "../../scripts/dep_resolver.py"
        )] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result

    def test_cli_analyze(self, tmp_path):
        error_file = tmp_path / "error.log"
        error_file.write_text(
            "Error: Cannot find module 'express'\n"
            "ModuleNotFoundError: No module named 'requests'\n"
        )
        result = self._run_cli("--analyze", str(error_file))
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert isinstance(data, dict)
        assert "issues" in data
        assert "actions" in data
        assert len(data["issues"]) >= 2
        assert len(data["actions"]) >= 2
