"""Tests for auto-fix integration failures (scripts/auto_fixer.py).

Validates:
  - parse_report extracts CRITICAL and WARNING issues from integration-checker JSON output
  - generate_fix_prompt creates targeted fix prompts with file paths and expected state
  - auto_fix orchestrates fix attempts with escalation after 2 failed attempts
  - Empty report returns success with no issues

Artifacts:
  - scripts/auto_fixer.py
  - tests/python/test_auto_fixer.py
"""

import json
import os
import subprocess
import sys

import pytest

# Allow importing from scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from auto_fixer import parse_report, generate_fix_prompt, auto_fix


# ---------------------------------------------------------------------------
# Sample integration-checker JSON report fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def report_with_critical():
    """Integration-checker report containing CRITICAL issues."""
    return {
        "status": "FAIL",
        "issues": [
            {
                "severity": "CRITICAL",
                "message": "Missing API endpoint handler for /api/users",
                "file": "src/routes/users.ts",
                "expected": "export function GET handler",
                "actual": "file does not export GET"
            },
            {
                "severity": "CRITICAL",
                "message": "Database schema mismatch in users table",
                "file": "prisma/schema.prisma",
                "expected": "email field with unique constraint",
                "actual": "email field missing"
            }
        ]
    }


@pytest.fixture
def report_with_warnings():
    """Integration-checker report containing WARNING issues."""
    return {
        "status": "WARN",
        "issues": [
            {
                "severity": "WARNING",
                "message": "Unused import in component file",
                "file": "src/components/Header.tsx",
                "expected": "no unused imports",
                "actual": "React imported but not used"
            },
            {
                "severity": "WARNING",
                "message": "Missing alt text on image",
                "file": "src/components/Logo.tsx",
                "expected": "img tag has alt attribute",
                "actual": "alt attribute missing"
            }
        ]
    }


@pytest.fixture
def report_mixed():
    """Integration-checker report with mixed CRITICAL and WARNING issues."""
    return {
        "status": "FAIL",
        "issues": [
            {
                "severity": "CRITICAL",
                "message": "Missing required export",
                "file": "src/index.ts",
                "expected": "default export",
                "actual": "no default export"
            },
            {
                "severity": "WARNING",
                "message": "Deprecated API usage",
                "file": "src/utils.ts",
                "expected": "use newApi()",
                "actual": "uses oldApi()"
            },
            {
                "severity": "INFO",
                "message": "Consider adding JSDoc",
                "file": "src/helpers.ts",
                "expected": "JSDoc comments",
                "actual": "no JSDoc"
            }
        ]
    }


@pytest.fixture
def empty_report():
    """Integration-checker report with no issues (all passed)."""
    return {
        "status": "PASS",
        "issues": []
    }


# ---------------------------------------------------------------------------
# Test: parse_report extracts CRITICAL issues
# ---------------------------------------------------------------------------

class TestParseCritical:
    """parse_report should extract CRITICAL issues from integration-checker output."""

    def test_parse_critical_extracts_critical_issues(self, report_with_critical):
        result = parse_report(report_with_critical)
        critical = [i for i in result if i["severity"] == "CRITICAL"]
        assert len(critical) == 2
        assert critical[0]["file"] == "src/routes/users.ts"
        assert critical[1]["file"] == "prisma/schema.prisma"

    def test_parse_critical_preserves_message(self, report_with_critical):
        result = parse_report(report_with_critical)
        critical = [i for i in result if i["severity"] == "CRITICAL"]
        assert "Missing API endpoint handler" in critical[0]["message"]

    def test_parse_critical_from_mixed_report(self, report_mixed):
        result = parse_report(report_mixed)
        critical = [i for i in result if i["severity"] == "CRITICAL"]
        assert len(critical) == 1
        assert critical[0]["file"] == "src/index.ts"


# ---------------------------------------------------------------------------
# Test: parse_report extracts WARNING issues
# ---------------------------------------------------------------------------

class TestParseWarning:
    """parse_report should extract WARNING issues from integration-checker output."""

    def test_parse_warning_extracts_warning_issues(self, report_with_warnings):
        result = parse_report(report_with_warnings)
        warnings = [i for i in result if i["severity"] == "WARNING"]
        assert len(warnings) == 2
        assert warnings[0]["file"] == "src/components/Header.tsx"
        assert warnings[1]["file"] == "src/components/Logo.tsx"

    def test_parse_warning_from_mixed_report(self, report_mixed):
        result = parse_report(report_mixed)
        warnings = [i for i in result if i["severity"] == "WARNING"]
        assert len(warnings) == 1
        assert warnings[0]["file"] == "src/utils.ts"

    def test_parse_excludes_info_severity(self, report_mixed):
        """parse_report should only extract CRITICAL and WARNING, not INFO."""
        result = parse_report(report_mixed)
        severities = {i["severity"] for i in result}
        assert "INFO" not in severities


# ---------------------------------------------------------------------------
# Test: generate_fix_prompt includes file paths and expected state
# ---------------------------------------------------------------------------

class TestGenerateFixPrompt:
    """generate_fix_prompt should produce a targeted fix prompt with file paths."""

    def test_prompt_includes_file_path(self):
        issue = {
            "severity": "CRITICAL",
            "message": "Missing API endpoint",
            "file": "src/routes/users.ts",
            "expected": "export function GET handler",
            "actual": "file does not export GET"
        }
        prompt = generate_fix_prompt(issue)
        assert "src/routes/users.ts" in prompt

    def test_prompt_includes_expected_state(self):
        issue = {
            "severity": "CRITICAL",
            "message": "Missing API endpoint",
            "file": "src/routes/users.ts",
            "expected": "export function GET handler",
            "actual": "file does not export GET"
        }
        prompt = generate_fix_prompt(issue)
        assert "export function GET handler" in prompt

    def test_prompt_includes_actual_state(self):
        issue = {
            "severity": "CRITICAL",
            "message": "Missing API endpoint",
            "file": "src/routes/users.ts",
            "expected": "export function GET handler",
            "actual": "file does not export GET"
        }
        prompt = generate_fix_prompt(issue)
        assert "file does not export GET" in prompt

    def test_prompt_includes_severity(self):
        issue = {
            "severity": "WARNING",
            "message": "Unused import",
            "file": "src/components/Header.tsx",
            "expected": "no unused imports",
            "actual": "React imported but not used"
        }
        prompt = generate_fix_prompt(issue)
        assert "WARNING" in prompt

    def test_prompt_is_nonempty_string(self):
        issue = {
            "severity": "CRITICAL",
            "message": "Something wrong",
            "file": "src/foo.ts",
            "expected": "correct state",
            "actual": "incorrect state"
        }
        prompt = generate_fix_prompt(issue)
        assert isinstance(prompt, str)
        assert len(prompt) > 0


# ---------------------------------------------------------------------------
# Test: auto_fix escalates after 2 failed attempts
# ---------------------------------------------------------------------------

class TestEscalationAfterTwo:
    """auto_fix should trigger human escalation after 2 failed fix attempts."""

    def test_escalation_after_2_attempts(self, report_with_critical):
        """Third attempt (attempt_count=3) should return escalation."""
        result = auto_fix(report_with_critical, max_attempts=2)
        # auto_fix should return a result dict with escalation info
        assert result is not None
        assert "escalated" in result
        assert result["escalated"] is True

    def test_escalation_includes_issues(self, report_with_critical):
        """Escalation result should reference the unresolved issues."""
        result = auto_fix(report_with_critical, max_attempts=2)
        assert "unresolved_issues" in result
        assert len(result["unresolved_issues"]) > 0

    def test_no_escalation_on_empty_report(self, empty_report):
        """auto_fix with empty report should succeed without escalation."""
        result = auto_fix(empty_report, max_attempts=2)
        assert result["escalated"] is False

    def test_escalation_message_present(self, report_with_critical):
        """Escalation result should include a human-readable message."""
        result = auto_fix(report_with_critical, max_attempts=2)
        assert "message" in result
        assert isinstance(result["message"], str)
        assert len(result["message"]) > 0


# ---------------------------------------------------------------------------
# Test: empty report returns success
# ---------------------------------------------------------------------------

class TestEmptyReport:
    """Empty report (no issues) should return success with no fix needed."""

    def test_empty_report_returns_success(self, empty_report):
        result = auto_fix(empty_report, max_attempts=2)
        assert result is not None
        assert result["escalated"] is False

    def test_empty_report_no_unresolved_issues(self, empty_report):
        result = auto_fix(empty_report, max_attempts=2)
        assert result.get("unresolved_issues", []) == []

    def test_empty_report_success_message(self, empty_report):
        result = auto_fix(empty_report, max_attempts=2)
        assert "message" in result

    def test_parse_empty_report(self, empty_report):
        result = parse_report(empty_report)
        assert result == []


# ---------------------------------------------------------------------------
# Test: CLI interface
# ---------------------------------------------------------------------------

class TestCLI:
    """CLI interface for auto_fixer.py."""

    def _run_cli(self, *args):
        cmd = [sys.executable, os.path.join(
            os.path.dirname(__file__), "../../scripts/auto_fixer.py"
        )] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result

    def test_cli_with_report_file(self, tmp_path):
        report = {
            "status": "PASS",
            "issues": []
        }
        report_file = tmp_path / "report.json"
        report_file.write_text(json.dumps(report))
        result = self._run_cli(str(report_file))
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["escalated"] is False

    def test_cli_with_critical_issues(self, tmp_path):
        report = {
            "status": "FAIL",
            "issues": [
                {
                    "severity": "CRITICAL",
                    "message": "Missing export",
                    "file": "src/index.ts",
                    "expected": "default export",
                    "actual": "no export"
                }
            ]
        }
        report_file = tmp_path / "report.json"
        report_file.write_text(json.dumps(report))
        result = self._run_cli(str(report_file))
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["escalated"] is True
