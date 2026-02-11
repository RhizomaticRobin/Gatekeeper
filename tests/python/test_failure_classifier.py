"""Tests for failure classification and adaptive retry (scripts/failure_classifier.py).

Validates:
  - classify_failure distinguishes 5 failure types by output pattern
  - retry_strategy returns retry for first attempt, modify_prompt for second, escalate for third
  - Flaky tests detected when same test alternates pass/fail in history
  - Classification result includes confidence score
  - Strategy includes explanation for the chosen action
"""

import json
import os
import subprocess
import sys

import pytest

# Allow importing from scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from failure_classifier import classify_failure, retry_strategy, detect_flaky_tests


class TestClassifyTestFailure:
    """classify_failure should identify test assertion failures."""

    def test_classify_test_failure_assertion_error(self):
        output = """
tests/test_example.py::test_add FAILED
E       AssertionError: expected 4 got 5
FAILED tests/test_example.py::test_add - AssertionError
"""
        result = classify_failure(output, exit_code=1)
        assert result["failure_type"] == "test_failure"
        assert "confidence" in result
        assert 0.0 <= result["confidence"] <= 1.0
        assert result["confidence"] >= 0.5

    def test_classify_test_failure_expected_got(self):
        output = "FAILED: expected True got False"
        result = classify_failure(output, exit_code=1)
        assert result["failure_type"] == "test_failure"

    def test_classify_test_failure_failed_keyword(self):
        output = "FAILED tests/test_foo.py::test_bar"
        result = classify_failure(output, exit_code=1)
        assert result["failure_type"] == "test_failure"


class TestClassifyBuildError:
    """classify_failure should identify build/import errors."""

    def test_classify_build_error_syntax(self):
        output = """
  File "app.py", line 10
    def foo(
          ^
SyntaxError: unexpected EOF while parsing
"""
        result = classify_failure(output, exit_code=1)
        assert result["failure_type"] == "build_error"
        assert "confidence" in result
        assert result["confidence"] >= 0.5

    def test_classify_build_error_import(self):
        output = "ImportError: No module named 'nonexistent'"
        result = classify_failure(output, exit_code=1)
        assert result["failure_type"] == "build_error"

    def test_classify_build_error_cannot_find_module(self):
        output = "Error: Cannot find module './missing-component'"
        result = classify_failure(output, exit_code=1)
        assert result["failure_type"] == "build_error"


class TestClassifyTimeout:
    """classify_failure should identify timeout failures."""

    def test_classify_timeout_exit_code_124(self):
        output = "Command timed out"
        result = classify_failure(output, exit_code=124)
        assert result["failure_type"] == "timeout"
        assert "confidence" in result
        assert result["confidence"] >= 0.7

    def test_classify_timeout_by_output(self):
        output = "Error: test execution timed out after 30s"
        result = classify_failure(output, exit_code=1)
        assert result["failure_type"] == "timeout"

    def test_classify_timeout_exit_code_alone(self):
        output = ""
        result = classify_failure(output, exit_code=124)
        assert result["failure_type"] == "timeout"


class TestClassifyScopeCreep:
    """classify_failure should identify scope creep (changes outside file scope)."""

    def test_classify_scope_creep(self):
        output = "Error: changes outside file_scope detected in src/unrelated.py"
        result = classify_failure(output, exit_code=1)
        assert result["failure_type"] == "scope_creep"
        assert "confidence" in result
        assert result["confidence"] >= 0.5


class TestRetryFirstAttempt:
    """retry_strategy should return 'retry' on first attempt."""

    def test_retry_first_attempt(self):
        result = retry_strategy("test_failure", attempt_count=1)
        assert result["action"] == "retry"
        assert "explanation" in result
        assert isinstance(result["explanation"], str)
        assert len(result["explanation"]) > 0


class TestRetrySecondAttempt:
    """retry_strategy should return 'modify_prompt' on second attempt."""

    def test_retry_second_attempt(self):
        result = retry_strategy("test_failure", attempt_count=2)
        assert result["action"] == "modify_prompt"
        assert "explanation" in result
        assert isinstance(result["explanation"], str)
        assert len(result["explanation"]) > 0


class TestRetryThirdAttempt:
    """retry_strategy should return 'escalate' on third (or more) attempt."""

    def test_retry_third_attempt(self):
        result = retry_strategy("test_failure", attempt_count=3)
        assert result["action"] == "escalate"
        assert "explanation" in result
        assert isinstance(result["explanation"], str)
        assert len(result["explanation"]) > 0

    def test_retry_fourth_attempt(self):
        result = retry_strategy("build_error", attempt_count=4)
        assert result["action"] == "escalate"
        assert "explanation" in result


class TestRetryStrategyAllTypes:
    """retry_strategy should work for all failure types."""

    @pytest.mark.parametrize("failure_type", [
        "test_failure", "build_error", "timeout", "scope_creep", "flaky_test"
    ])
    def test_retry_strategy_all_types_first_attempt(self, failure_type):
        result = retry_strategy(failure_type, attempt_count=1)
        assert result["action"] == "retry"

    @pytest.mark.parametrize("failure_type", [
        "test_failure", "build_error", "timeout", "scope_creep", "flaky_test"
    ])
    def test_retry_strategy_all_types_second_attempt(self, failure_type):
        result = retry_strategy(failure_type, attempt_count=2)
        assert result["action"] == "modify_prompt"

    @pytest.mark.parametrize("failure_type", [
        "test_failure", "build_error", "timeout", "scope_creep", "flaky_test"
    ])
    def test_retry_strategy_all_types_third_attempt(self, failure_type):
        result = retry_strategy(failure_type, attempt_count=3)
        assert result["action"] == "escalate"


class TestFlakyDetection:
    """detect_flaky_tests should identify tests that alternate pass/fail."""

    def test_flaky_detection_alternating(self):
        history = [
            {"test_name": "test_foo", "passed": True},
            {"test_name": "test_foo", "passed": False},
            {"test_name": "test_foo", "passed": True},
            {"test_name": "test_foo", "passed": False},
        ]
        flaky = detect_flaky_tests(history)
        assert "test_foo" in flaky

    def test_flaky_detection_consistent_pass(self):
        history = [
            {"test_name": "test_bar", "passed": True},
            {"test_name": "test_bar", "passed": True},
            {"test_name": "test_bar", "passed": True},
        ]
        flaky = detect_flaky_tests(history)
        assert "test_bar" not in flaky

    def test_flaky_detection_consistent_fail(self):
        history = [
            {"test_name": "test_baz", "passed": False},
            {"test_name": "test_baz", "passed": False},
            {"test_name": "test_baz", "passed": False},
        ]
        flaky = detect_flaky_tests(history)
        assert "test_baz" not in flaky

    def test_flaky_detection_multiple_tests(self):
        history = [
            {"test_name": "test_stable", "passed": True},
            {"test_name": "test_stable", "passed": True},
            {"test_name": "test_flaky", "passed": True},
            {"test_name": "test_flaky", "passed": False},
            {"test_name": "test_flaky", "passed": True},
        ]
        flaky = detect_flaky_tests(history)
        assert "test_flaky" in flaky
        assert "test_stable" not in flaky

    def test_flaky_detection_empty_history(self):
        flaky = detect_flaky_tests([])
        assert len(flaky) == 0


class TestClassifyFlakyTest:
    """classify_failure with flaky_history should return flaky_test type."""

    def test_classify_with_flaky_history(self):
        output = "FAILED tests/test_example.py::test_intermittent"
        history = [
            {"test_name": "test_intermittent", "passed": True},
            {"test_name": "test_intermittent", "passed": False},
            {"test_name": "test_intermittent", "passed": True},
        ]
        result = classify_failure(output, exit_code=1, test_history=history)
        assert result["failure_type"] == "flaky_test"


class TestConfidenceScore:
    """Classification should always include a confidence score between 0 and 1."""

    def test_confidence_present_and_valid(self):
        test_cases = [
            ("FAILED test_x - AssertionError", 1),
            ("SyntaxError: invalid syntax", 1),
            ("timed out", 124),
            ("changes outside file_scope detected", 1),
        ]
        for output, exit_code in test_cases:
            result = classify_failure(output, exit_code)
            assert "confidence" in result, f"Missing confidence for: {output}"
            assert isinstance(result["confidence"], (int, float))
            assert 0.0 <= result["confidence"] <= 1.0


class TestStrategyExplanation:
    """Strategy should always include a non-empty explanation."""

    def test_explanation_present(self):
        for attempt in [1, 2, 3]:
            result = retry_strategy("test_failure", attempt)
            assert "explanation" in result
            assert isinstance(result["explanation"], str)
            assert len(result["explanation"]) > 0


class TestCLI:
    """CLI interface for failure_classifier.py."""

    def _run_cli(self, *args):
        cmd = [sys.executable, os.path.join(
            os.path.dirname(__file__), "../../scripts/failure_classifier.py"
        )] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result

    def test_cli_classify(self):
        result = self._run_cli(
            "--classify",
            "--output", "FAILED test_x - AssertionError",
            "--exit-code", "1"
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["failure_type"] == "test_failure"
        assert "confidence" in data

    def test_cli_strategy(self):
        result = self._run_cli(
            "--strategy",
            "--failure-type", "test_failure",
            "--attempt", "1"
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["action"] == "retry"
        assert "explanation" in data
