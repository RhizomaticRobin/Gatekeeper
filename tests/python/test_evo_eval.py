"""Tests for cascade evaluator with multi-dimensional metrics (scripts/evo_eval.py).

Validates:
  - CascadeEvaluator.evaluate() runs a 3-stage cascade: collect-only check, partial test run, full test suite
  - Stage 1 rejects approaches whose tests cannot even be collected (syntax errors, missing imports)
  - Stage 2 runs first 3 tests and rejects if pass_rate < 0.5
  - Stage 3 runs the full test command and extracts comprehensive metrics
  - Metrics include test_pass_rate, duration_s, complexity, todo_count, error_count, stage, and artifacts
  - Artifacts capture test_output and error_trace for feedback into evolution prompts
  - CLI supports --evaluate with optional --source-dirs and --timeout

Artifacts:
  - scripts/evo_eval.py
  - tests/python/test_evo_eval.py
"""

import json
import os
import subprocess
import sys

import pytest

# Allow importing from scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from unittest.mock import patch, MagicMock
from evo_eval import CascadeEvaluator


# ---------------------------------------------------------------------------
# Helpers for creating mock subprocess results
# ---------------------------------------------------------------------------

def _make_completed_process(stdout="", stderr="", returncode=0):
    """Create a mock subprocess.CompletedProcess."""
    result = MagicMock(spec=subprocess.CompletedProcess)
    result.stdout = stdout
    result.stderr = stderr
    result.returncode = returncode
    return result


# ---------------------------------------------------------------------------
# Pytest collect-only output fixtures
# ---------------------------------------------------------------------------

COLLECT_ONLY_SUCCESS = """\
<Module tests/test_example.py>
  <Function test_alpha>
  <Function test_beta>
  <Function test_gamma>
  <Function test_delta>
  <Function test_epsilon>

5 tests collected in 0.12s
"""

COLLECT_ONLY_FAILURE = """\
ERROR collecting tests/test_broken.py
  ImportError: No module named 'nonexistent_package'
  SyntaxError: invalid syntax (test_broken.py, line 5)

0 tests collected, 1 error in 0.08s
"""

PARTIAL_RUN_0_OF_3 = """\
============================= test session starts ==============================
collected 3 items

tests/test_example.py::test_alpha FAILED
tests/test_example.py::test_beta FAILED
tests/test_example.py::test_gamma FAILED

=========================== short test summary info ============================
FAILED tests/test_example.py::test_alpha
FAILED tests/test_example.py::test_beta
FAILED tests/test_example.py::test_gamma
============================== 3 failed in 1.20s ==============================
"""

PARTIAL_RUN_2_OF_3 = """\
============================= test session starts ==============================
collected 3 items

tests/test_example.py::test_alpha PASSED
tests/test_example.py::test_beta FAILED
tests/test_example.py::test_gamma PASSED

=========================== short test summary info ============================
FAILED tests/test_example.py::test_beta
========================= 2 passed, 1 failed in 1.50s =========================
"""

FULL_RUN_ALL_PASSED = """\
============================= test session starts ==============================
collected 5 items

tests/test_example.py::test_alpha PASSED
tests/test_example.py::test_beta PASSED
tests/test_example.py::test_gamma PASSED
tests/test_example.py::test_delta PASSED
tests/test_example.py::test_epsilon PASSED

============================== 5 passed in 3.45s ==============================
"""

FULL_RUN_WITH_ERRORS = """\
============================= test session starts ==============================
collected 5 items

tests/test_example.py::test_alpha PASSED
tests/test_example.py::test_beta PASSED
tests/test_example.py::test_gamma PASSED
tests/test_example.py::test_delta FAILED
tests/test_example.py::test_epsilon ERROR

=========================== short test summary info ============================
FAILED tests/test_example.py::test_delta - AssertionError
ERROR tests/test_example.py::test_epsilon
Traceback (most recent call last):
  File "tests/test_example.py", line 42, in test_epsilon
    raise RuntimeError("something went wrong")
RuntimeError: something went wrong
========================= 3 passed, 1 failed, 1 error in 2.50s ===============
"""


# ---------------------------------------------------------------------------
# Test: Stage 1 rejects unparseable (syntax errors, missing imports)
# ---------------------------------------------------------------------------

class TestStage1:
    @patch("evo_eval.subprocess.run")
    def test_stage1_rejects_unparseable(self, mock_run):
        """Stage 1 collect-only returns exit code 1 (syntax error).
        Evaluator should return stage=1, test_pass_rate=0.0."""
        mock_run.return_value = _make_completed_process(
            stdout=COLLECT_ONLY_FAILURE,
            stderr="SyntaxError: invalid syntax",
            returncode=1,
        )

        evaluator = CascadeEvaluator()
        result = evaluator.evaluate("pytest tests/test_broken.py -v")

        assert result["stage"] == 1
        assert result["test_pass_rate"] == 0.0
        # Should only call subprocess once (collect-only), not proceed further
        assert mock_run.call_count == 1

    @patch("evo_eval.subprocess.run")
    def test_stage1_passes_valid(self, mock_run):
        """Stage 1 collect-only succeeds (exit code 0).
        Evaluator should proceed to stage 2 (at least 2 subprocess calls)."""
        # Call 1: collect-only (stage 1) succeeds
        # Call 2: partial run (stage 2) -- we let it pass too
        # Call 3: full run (stage 3)
        mock_run.side_effect = [
            _make_completed_process(stdout=COLLECT_ONLY_SUCCESS, returncode=0),
            _make_completed_process(stdout=PARTIAL_RUN_2_OF_3, returncode=1),
            _make_completed_process(stdout=FULL_RUN_ALL_PASSED, returncode=0),
        ]

        evaluator = CascadeEvaluator()
        result = evaluator.evaluate("pytest tests/test_example.py -v")

        # Should have proceeded past stage 1
        assert result["stage"] >= 2
        assert mock_run.call_count >= 2


# ---------------------------------------------------------------------------
# Test: Stage 2 rejects low pass rate
# ---------------------------------------------------------------------------

class TestStage2:
    @patch("evo_eval.subprocess.run")
    def test_stage2_rejects_low_pass_rate(self, mock_run):
        """Stage 2 runs first 3 tests, all fail (0/3 passed).
        pass_rate = 0.0 < 0.5 threshold, so should reject with stage=2."""
        mock_run.side_effect = [
            # Stage 1: collect-only succeeds
            _make_completed_process(stdout=COLLECT_ONLY_SUCCESS, returncode=0),
            # Stage 2: partial run, 0 of 3 passed
            _make_completed_process(stdout=PARTIAL_RUN_0_OF_3, returncode=1),
        ]

        evaluator = CascadeEvaluator()
        result = evaluator.evaluate("pytest tests/test_example.py -v")

        assert result["stage"] == 2
        assert result["test_pass_rate"] < 0.5
        # Should stop after stage 2 (2 calls: collect-only + partial run)
        assert mock_run.call_count == 2

    @patch("evo_eval.subprocess.run")
    def test_stage2_passes_partial(self, mock_run):
        """Stage 2 runs first 3 tests, 2 of 3 pass (pass_rate ~0.67 >= 0.5).
        Should proceed to stage 3."""
        mock_run.side_effect = [
            # Stage 1: collect-only succeeds
            _make_completed_process(stdout=COLLECT_ONLY_SUCCESS, returncode=0),
            # Stage 2: partial run, 2 of 3 passed
            _make_completed_process(stdout=PARTIAL_RUN_2_OF_3, returncode=1),
            # Stage 3: full run
            _make_completed_process(stdout=FULL_RUN_ALL_PASSED, returncode=0),
        ]

        evaluator = CascadeEvaluator()
        result = evaluator.evaluate("pytest tests/test_example.py -v")

        # Should have proceeded to stage 3
        assert result["stage"] == 3
        assert mock_run.call_count == 3


# ---------------------------------------------------------------------------
# Test: Stage 3 full metrics
# ---------------------------------------------------------------------------

class TestStage3:
    @patch("evo_eval.subprocess.run")
    def test_stage3_full_metrics(self, mock_run):
        """Full cascade passes all stages, returns comprehensive metrics."""
        mock_run.side_effect = [
            # Stage 1: collect-only succeeds
            _make_completed_process(stdout=COLLECT_ONLY_SUCCESS, returncode=0),
            # Stage 2: partial run, 2/3 pass (above threshold)
            _make_completed_process(stdout=PARTIAL_RUN_2_OF_3, returncode=1),
            # Stage 3: full run, 5/5 pass
            _make_completed_process(stdout=FULL_RUN_ALL_PASSED, returncode=0),
        ]

        evaluator = CascadeEvaluator()
        result = evaluator.evaluate("pytest tests/test_example.py -v")

        assert result["stage"] == 3
        assert result["test_pass_rate"] == 1.0
        assert result["duration_s"] == pytest.approx(3.45, abs=0.01)
        assert "complexity" in result
        assert "todo_count" in result
        assert "error_count" in result
        assert "artifacts" in result
        assert "test_output" in result["artifacts"]


# ---------------------------------------------------------------------------
# Test: Timeout handling
# ---------------------------------------------------------------------------

class TestTimeout:
    @patch("evo_eval.subprocess.run")
    def test_timeout_handling(self, mock_run):
        """subprocess.run raises TimeoutExpired.
        Should return partial metrics with timeout indicator."""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd="pytest tests/ -v", timeout=300
        )

        evaluator = CascadeEvaluator(config={"timeout": 300})
        result = evaluator.evaluate("pytest tests/ -v")

        # Should still return a result dict, not raise
        assert "stage" in result
        assert "artifacts" in result
        assert result["artifacts"].get("timeout") is True


# ---------------------------------------------------------------------------
# Test: Metrics extraction from pytest output
# ---------------------------------------------------------------------------

class TestMetricsExtraction:
    def test_metrics_extraction(self):
        """_extract_test_metrics parses pytest summary line correctly."""
        evaluator = CascadeEvaluator()
        output = "3 passed, 1 failed in 2.50s"
        metrics = evaluator._extract_test_metrics(output)

        assert metrics["passed"] == 3
        assert metrics["failed"] == 1
        assert metrics["pass_rate"] == pytest.approx(0.75, abs=0.01)
        assert metrics["duration_s"] == pytest.approx(2.50, abs=0.01)


# ---------------------------------------------------------------------------
# Test: Code metrics from source directories
# ---------------------------------------------------------------------------

class TestCodeMetrics:
    def test_code_metrics(self, tmp_path):
        """_extract_code_metrics counts LOC and TODOs in .py files."""
        # Create fixture source files
        source_dir = tmp_path / "src"
        source_dir.mkdir()

        (source_dir / "module_a.py").write_text(
            "# Module A\n"
            "def foo():\n"
            "    # TODO: implement this\n"
            "    pass\n"
            "\n"
            "def bar():\n"
            "    # FIXME: broken logic\n"
            "    return 42\n"
        )

        (source_dir / "module_b.py").write_text(
            "import os\n"
            "# todo: clean up\n"
            "x = 1\n"
        )

        # Non-py file should be ignored
        (source_dir / "readme.txt").write_text("This is not Python\nTODO: nothing\n")

        evaluator = CascadeEvaluator()
        metrics = evaluator._extract_code_metrics([str(source_dir)])

        # LOC: non-empty lines from .py files
        # module_a: 7 non-empty lines, module_b: 3 non-empty lines = 10 total
        assert metrics["complexity"] > 0
        # TODOs: "TODO: implement this" + "todo: clean up" = 2 (case-insensitive)
        assert metrics["todo_count"] == 2
        # FIXMEs: "FIXME: broken logic" = 1
        assert metrics["fixme_count"] == 1


# ---------------------------------------------------------------------------
# Test: Artifact capture and truncation
# ---------------------------------------------------------------------------

class TestArtifactCapture:
    def test_artifact_capture(self):
        """_capture_artifacts extracts traceback and truncates long output."""
        evaluator = CascadeEvaluator()

        long_output = "x" * 5000  # Exceeds 2000 char limit
        traceback_output = (
            "some test output\n"
            "Traceback (most recent call last):\n"
            "  File \"test.py\", line 10, in test_func\n"
            "    assert False\n"
            "AssertionError\n"
            "more output\n"
        )

        # Test truncation of long output
        artifacts = evaluator._capture_artifacts(long_output, exit_code=1)
        assert len(artifacts["test_output"]) <= 2000

        # Test traceback extraction
        artifacts2 = evaluator._capture_artifacts(traceback_output, exit_code=1)
        assert "Traceback" in artifacts2["error_trace"]
        assert len(artifacts2["error_trace"]) <= 1000


# ---------------------------------------------------------------------------
# Test: Empty source dirs
# ---------------------------------------------------------------------------

class TestEmptySourceDirs:
    @patch("evo_eval.subprocess.run")
    def test_empty_source_dirs(self, mock_run):
        """evaluate with source_dirs=None returns complexity=0, todo_count=0."""
        mock_run.side_effect = [
            # Stage 1: collect-only succeeds
            _make_completed_process(stdout=COLLECT_ONLY_SUCCESS, returncode=0),
            # Stage 2: 2/3 pass
            _make_completed_process(stdout=PARTIAL_RUN_2_OF_3, returncode=1),
            # Stage 3: all pass
            _make_completed_process(stdout=FULL_RUN_ALL_PASSED, returncode=0),
        ]

        evaluator = CascadeEvaluator()
        result = evaluator.evaluate("pytest tests/test_example.py -v", source_dirs=None)

        assert result["complexity"] == 0
        assert result["todo_count"] == 0


# ---------------------------------------------------------------------------
# Test: CLI --evaluate
# ---------------------------------------------------------------------------

class TestCLI:
    @patch("evo_eval.subprocess.run")
    def test_cli_evaluate(self, mock_run):
        """CLI --evaluate outputs valid JSON with test_pass_rate and stage."""
        mock_run.side_effect = [
            # Stage 1: collect-only succeeds
            _make_completed_process(stdout=COLLECT_ONLY_SUCCESS, returncode=0),
            # Stage 2: 2/3 pass
            _make_completed_process(stdout=PARTIAL_RUN_2_OF_3, returncode=1),
            # Stage 3: all pass
            _make_completed_process(stdout=FULL_RUN_ALL_PASSED, returncode=0),
        ]

        # Import the main function and test CLI
        from evo_eval import main
        import io
        from unittest.mock import patch as mock_patch

        with mock_patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            with mock_patch("sys.argv", ["evo_eval.py", "--evaluate", "pytest tests/ -v"]):
                main()

        output = mock_stdout.getvalue().strip()
        data = json.loads(output)
        assert "test_pass_rate" in data
        assert "stage" in data
