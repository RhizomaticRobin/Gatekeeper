"""Tests for scripts/resilience.py — Resilience module with stuck detection, circuit breaker, and budget checks."""

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta

import pytest

# Import from scripts/ (conftest.py ensures scripts/ is on sys.path)
from resilience import ResilienceManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager(tmp_dir=None):
    """Create a ResilienceManager with a temporary state path."""
    if tmp_dir is None:
        tmp_dir = tempfile.mkdtemp()
    state_path = os.path.join(tmp_dir, "vgl-resilience.json")
    return ResilienceManager(state_path)


# ---------------------------------------------------------------------------
# T1  test_record_failure_increments
# ---------------------------------------------------------------------------

class TestRecordFailureIncrements:
    def test_record_failure_increments(self):
        """record_failure increments the per-task counter and total_failures."""
        mgr = _make_manager()
        mgr.record_failure("1.1")
        mgr.record_failure("1.1")
        mgr.record_failure("1.1")
        assert mgr.state.task_failures["1.1"] == 3
        assert mgr.state.total_failures == 3
        assert mgr.state.last_failure_task == "1.1"

    def test_record_failure_appends_to_window(self):
        """record_failure appends entries to the failure_window."""
        mgr = _make_manager()
        mgr.record_failure("1.1", error="import error", files=["foo.py"])
        assert len(mgr.state.failure_window) == 1
        entry = mgr.state.failure_window[0]
        assert entry["task_id"] == "1.1"
        assert entry["error"] == "import error"
        assert "foo.py" in entry["files"]
        assert "timestamp" in entry

    def test_failure_window_capped_at_20(self):
        """failure_window never exceeds 20 entries (FIFO)."""
        mgr = _make_manager()
        for i in range(25):
            mgr.record_failure("1.1", error=f"error {i}")
        assert len(mgr.state.failure_window) == 20
        # The oldest entries should have been removed
        assert mgr.state.failure_window[0]["error"] == "error 5"

    def test_record_failure_sets_started_at(self):
        """First record_failure sets started_at if not already set."""
        mgr = _make_manager()
        assert mgr.state.started_at is None
        mgr.record_failure("1.1")
        assert mgr.state.started_at is not None


# ---------------------------------------------------------------------------
# T2  test_record_success_resets
# ---------------------------------------------------------------------------

class TestRecordSuccessResets:
    def test_record_success_resets(self):
        """record_success resets the per-task failure counter to 0."""
        mgr = _make_manager()
        mgr.record_failure("1.1")
        mgr.record_failure("1.1")
        assert mgr.state.task_failures["1.1"] == 2
        mgr.record_success("1.1")
        assert mgr.state.task_failures["1.1"] == 0

    def test_record_success_does_not_affect_total(self):
        """record_success does not decrement total_failures."""
        mgr = _make_manager()
        mgr.record_failure("1.1")
        mgr.record_failure("1.1")
        assert mgr.state.total_failures == 2
        mgr.record_success("1.1")
        # total_failures should remain unchanged
        assert mgr.state.total_failures == 2

    def test_record_success_nonexistent_task(self):
        """record_success on a task with no failures does not error."""
        mgr = _make_manager()
        mgr.record_success("1.1")  # should not raise
        assert mgr.state.task_failures.get("1.1", 0) == 0


# ---------------------------------------------------------------------------
# T3  test_stuck_detection
# ---------------------------------------------------------------------------

class TestStuckDetection:
    def test_stuck_detection(self):
        """check_stuck returns True when task failures reach threshold."""
        mgr = _make_manager()
        mgr.record_failure("1.1")
        mgr.record_failure("1.1")
        mgr.record_failure("1.1")
        is_stuck, count, msg = mgr.check_stuck("1.1", threshold=3)
        assert is_stuck is True
        assert count == 3
        assert "1.1" in msg
        assert "3" in msg

    def test_stuck_below_threshold(self):
        """check_stuck returns False when task failures are below threshold."""
        mgr = _make_manager()
        mgr.record_failure("1.1")
        mgr.record_failure("1.1")
        is_stuck, count, msg = mgr.check_stuck("1.1", threshold=3)
        assert is_stuck is False
        assert count == 2

    def test_stuck_message_format(self):
        """Stuck message matches expected format."""
        mgr = _make_manager()
        for _ in range(3):
            mgr.record_failure("2.1")
        is_stuck, count, msg = mgr.check_stuck("2.1", threshold=3)
        assert is_stuck is True
        expected = "VGL: Stuck on task 2.1 (3 consecutive failures, threshold: 3)"
        assert msg == expected


# ---------------------------------------------------------------------------
# T4  test_circuit_breaker_trips
# ---------------------------------------------------------------------------

class TestCircuitBreakerTrips:
    def test_circuit_breaker_trips(self):
        """check_circuit_breaker returns True when total failures reach threshold."""
        mgr = _make_manager()
        mgr.record_failure("1.1")
        mgr.record_failure("1.2")
        mgr.record_failure("2.1")
        mgr.record_failure("2.2")
        mgr.record_failure("3.1")
        is_tripped, count, msg = mgr.check_circuit_breaker(threshold=5)
        assert is_tripped is True
        assert count == 5
        assert "5" in msg

    def test_circuit_breaker_below_threshold(self):
        """check_circuit_breaker returns False when below threshold."""
        mgr = _make_manager()
        mgr.record_failure("1.1")
        mgr.record_failure("1.2")
        is_tripped, count, msg = mgr.check_circuit_breaker(threshold=5)
        assert is_tripped is False
        assert count == 2

    def test_circuit_breaker_message_format(self):
        """Circuit breaker message matches expected format."""
        mgr = _make_manager()
        for i in range(5):
            mgr.record_failure(f"task-{i}")
        is_tripped, count, msg = mgr.check_circuit_breaker(threshold=5)
        assert is_tripped is True
        expected = "VGL: Circuit breaker tripped (5 total failures, threshold: 5)"
        assert msg == expected


# ---------------------------------------------------------------------------
# T5  test_budget_checks
# ---------------------------------------------------------------------------

class TestBudgetChecks:
    def test_budget_iterations_exceeded(self):
        """check_budget detects when iterations exceed max."""
        mgr = _make_manager()
        mgr.state.total_iterations = 50
        exceeded, reason, msg = mgr.check_budget(max_iterations=50, timeout_hours=8)
        assert exceeded is True
        assert reason == "iterations"
        assert "50" in msg

    def test_budget_iterations_within_limits(self):
        """check_budget returns False when within iteration limits."""
        mgr = _make_manager()
        mgr.state.total_iterations = 10
        exceeded, reason, msg = mgr.check_budget(max_iterations=50, timeout_hours=8)
        assert exceeded is False

    def test_budget_timeout_exceeded(self):
        """check_budget detects when timeout has been exceeded."""
        mgr = _make_manager()
        mgr.state.total_iterations = 0
        # Set started_at to 9 hours ago
        past = datetime.now() - timedelta(hours=9)
        mgr.state.started_at = past.isoformat()
        exceeded, reason, msg = mgr.check_budget(max_iterations=50, timeout_hours=8)
        assert exceeded is True
        assert reason == "timeout"
        assert "8" in msg  # max hours should be in message

    def test_budget_no_started_at(self):
        """check_budget with no started_at does not trip timeout."""
        mgr = _make_manager()
        mgr.state.total_iterations = 0
        mgr.state.started_at = None
        exceeded, reason, msg = mgr.check_budget(max_iterations=50, timeout_hours=8)
        assert exceeded is False

    def test_budget_iteration_message_format(self):
        """Budget iteration message matches expected format."""
        mgr = _make_manager()
        mgr.state.total_iterations = 50
        exceeded, reason, msg = mgr.check_budget(max_iterations=50, timeout_hours=8)
        assert exceeded is True
        expected = "VGL: Budget exceeded (50 iterations, max: 50)"
        assert msg == expected

    def test_budget_timeout_message_format(self):
        """Budget timeout message matches expected format."""
        mgr = _make_manager()
        mgr.state.total_iterations = 0
        past = datetime.now() - timedelta(hours=9)
        mgr.state.started_at = past.isoformat()
        exceeded, reason, msg = mgr.check_budget(max_iterations=50, timeout_hours=8)
        assert exceeded is True
        # Message should contain elapsed hours and max hours
        assert "elapsed" in msg
        assert "max: 8" in msg


# ---------------------------------------------------------------------------
# T6  test_analyze_failures
# ---------------------------------------------------------------------------

class TestAnalyzeFailures:
    def test_analyze_failures_patterns(self):
        """analyze_failures identifies repeated error patterns."""
        mgr = _make_manager()
        # Record 5 failures with the same error message
        for i in range(5):
            mgr.record_failure("1.1", error="ModuleNotFoundError: No module named 'foo'",
                               files=["scripts/foo.py"])
        analysis = mgr.analyze_failures()
        assert "repeated_errors" in analysis
        assert len(analysis["repeated_errors"]) > 0
        # The repeated error should be identified
        found = False
        for err_entry in analysis["repeated_errors"]:
            if "ModuleNotFoundError" in err_entry.get("error", ""):
                found = True
                break
        assert found, f"Expected ModuleNotFoundError in repeated_errors, got: {analysis['repeated_errors']}"

    def test_analyze_failures_affected_files(self):
        """analyze_failures identifies most-affected files."""
        mgr = _make_manager()
        for i in range(3):
            mgr.record_failure("1.1", error="error", files=["scripts/main.py"])
        mgr.record_failure("1.2", error="error", files=["scripts/other.py"])
        analysis = mgr.analyze_failures()
        assert "affected_files" in analysis
        # scripts/main.py should appear more frequently
        found = False
        for file_entry in analysis["affected_files"]:
            if file_entry.get("file") == "scripts/main.py":
                found = True
                assert file_entry.get("count", 0) >= 3
                break
        assert found, f"Expected scripts/main.py in affected_files, got: {analysis['affected_files']}"

    def test_analyze_failures_failing_phases(self):
        """analyze_failures identifies failing task prefixes (phases)."""
        mgr = _make_manager()
        mgr.record_failure("1.1", error="e")
        mgr.record_failure("1.2", error="e")
        mgr.record_failure("1.3", error="e")
        mgr.record_failure("2.1", error="e")
        analysis = mgr.analyze_failures()
        assert "failing_phases" in analysis
        # Phase "1" should be the most common
        found = False
        for phase_entry in analysis["failing_phases"]:
            if phase_entry.get("phase") == "1":
                found = True
                assert phase_entry.get("count", 0) >= 3
                break
        assert found, f"Expected phase '1' in failing_phases, got: {analysis['failing_phases']}"

    def test_analyze_failures_empty_window(self):
        """analyze_failures with empty window returns empty analysis."""
        mgr = _make_manager()
        analysis = mgr.analyze_failures()
        assert "repeated_errors" in analysis
        assert len(analysis["repeated_errors"]) == 0


# ---------------------------------------------------------------------------
# T5b  test_check_all
# ---------------------------------------------------------------------------

class TestCheckAll:
    def test_check_all_within_limits(self):
        """check_all returns (False, None, None) when everything is OK."""
        mgr = _make_manager()
        config = {
            "stuck_threshold": 3,
            "circuit_breaker_threshold": 5,
            "max_vgl_iterations": 50,
            "timeout_hours": 8,
        }
        triggered, check_name, msg = mgr.check_all("1.1", config)
        assert triggered is False
        assert check_name is None
        assert msg is None

    def test_check_all_stuck(self):
        """check_all detects stuck condition."""
        mgr = _make_manager()
        for _ in range(3):
            mgr.record_failure("1.1")
        config = {
            "stuck_threshold": 3,
            "circuit_breaker_threshold": 5,
            "max_vgl_iterations": 50,
            "timeout_hours": 8,
        }
        triggered, check_name, msg = mgr.check_all("1.1", config)
        assert triggered is True
        assert check_name is not None
        assert msg is not None


# ---------------------------------------------------------------------------
# T5c  test_reset_clears_state
# ---------------------------------------------------------------------------

class TestResetClearsState:
    def test_reset_clears_state(self):
        """reset() clears all failure state."""
        mgr = _make_manager()
        mgr.record_failure("1.1")
        mgr.record_failure("1.2")
        mgr.record_failure("1.1")
        mgr.state.total_iterations = 10
        mgr.reset()
        assert mgr.state.task_failures == {}
        assert mgr.state.total_failures == 0
        assert mgr.state.failure_window == []
        assert mgr.state.total_iterations == 0
        assert mgr.state.started_at is None
        assert mgr.state.last_failure_task is None


# ---------------------------------------------------------------------------
# T7  test_persistence_roundtrip
# ---------------------------------------------------------------------------

class TestPersistenceRoundtrip:
    def test_persistence_roundtrip(self):
        """save→load roundtrip preserves all state."""
        tmp_dir = tempfile.mkdtemp()
        state_path = os.path.join(tmp_dir, "vgl-resilience.json")

        mgr1 = ResilienceManager(state_path)
        mgr1.record_failure("1.1", error="import error", files=["foo.py"])
        mgr1.record_failure("1.1", error="type error", files=["bar.py"])
        mgr1.record_failure("2.1", error="syntax error")
        mgr1.state.total_iterations = 7
        mgr1.save()

        # Create new instance and load
        mgr2 = ResilienceManager(state_path)
        mgr2.load()

        assert mgr2.state.task_failures == mgr1.state.task_failures
        assert mgr2.state.total_failures == mgr1.state.total_failures
        assert len(mgr2.state.failure_window) == len(mgr1.state.failure_window)
        assert mgr2.state.total_iterations == mgr1.state.total_iterations
        assert mgr2.state.started_at == mgr1.state.started_at
        assert mgr2.state.last_failure_task == mgr1.state.last_failure_task

    def test_persistence_creates_file(self):
        """save creates the JSON file on disk."""
        tmp_dir = tempfile.mkdtemp()
        state_path = os.path.join(tmp_dir, "vgl-resilience.json")

        mgr = ResilienceManager(state_path)
        mgr.record_failure("1.1")
        mgr.save()

        assert os.path.exists(state_path)
        with open(state_path) as f:
            data = json.load(f)
        assert data["task_failures"]["1.1"] == 1

    def test_load_nonexistent_file(self):
        """load on nonexistent file does not error (uses default state)."""
        tmp_dir = tempfile.mkdtemp()
        state_path = os.path.join(tmp_dir, "nonexistent.json")
        mgr = ResilienceManager(state_path)
        mgr.load()  # should not raise
        assert mgr.state.total_failures == 0


# ---------------------------------------------------------------------------
# T8  test_cli_integration
# ---------------------------------------------------------------------------

class TestCLIIntegration:
    def _run_cli(self, args, state_path):
        """Helper to run resilience.py CLI."""
        script = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "resilience.py")
        script = os.path.abspath(script)
        cmd = [sys.executable, script, "--state-path", state_path] + args
        return subprocess.run(cmd, capture_output=True, text=True)

    def test_cli_record_failure(self):
        """CLI --record-failure updates state file."""
        tmp_dir = tempfile.mkdtemp()
        state_path = os.path.join(tmp_dir, "vgl-resilience.json")

        result = self._run_cli(["--record-failure", "1.1", "--error", "test error"], state_path)
        assert result.returncode == 0

        # Verify state file was created and updated
        assert os.path.exists(state_path)
        with open(state_path) as f:
            data = json.load(f)
        assert data["task_failures"]["1.1"] == 1

    def test_cli_record_success(self):
        """CLI --record-success resets task failure count."""
        tmp_dir = tempfile.mkdtemp()
        state_path = os.path.join(tmp_dir, "vgl-resilience.json")

        # Record some failures first
        self._run_cli(["--record-failure", "1.1"], state_path)
        self._run_cli(["--record-failure", "1.1"], state_path)

        # Then record success
        result = self._run_cli(["--record-success", "1.1"], state_path)
        assert result.returncode == 0

        with open(state_path) as f:
            data = json.load(f)
        assert data["task_failures"]["1.1"] == 0

    def test_cli_check_stuck_below_threshold(self):
        """CLI --check-stuck exits 0 when below threshold."""
        tmp_dir = tempfile.mkdtemp()
        state_path = os.path.join(tmp_dir, "vgl-resilience.json")

        # Record 2 failures (below default threshold of 3)
        self._run_cli(["--record-failure", "1.1"], state_path)
        self._run_cli(["--record-failure", "1.1"], state_path)

        result = self._run_cli(["--check-stuck", "1.1", "--threshold", "3"], state_path)
        assert result.returncode == 0

    def test_cli_check_stuck_at_threshold(self):
        """CLI --check-stuck exits 1 when at threshold."""
        tmp_dir = tempfile.mkdtemp()
        state_path = os.path.join(tmp_dir, "vgl-resilience.json")

        # Record 3 failures (at threshold)
        self._run_cli(["--record-failure", "1.1"], state_path)
        self._run_cli(["--record-failure", "1.1"], state_path)
        self._run_cli(["--record-failure", "1.1"], state_path)

        result = self._run_cli(["--check-stuck", "1.1", "--threshold", "3"], state_path)
        assert result.returncode == 1
        assert "Stuck" in result.stdout or "stuck" in result.stdout.lower()

    def test_cli_check_all_within_limits(self):
        """CLI --check-all exits 0 when within all limits."""
        tmp_dir = tempfile.mkdtemp()
        state_path = os.path.join(tmp_dir, "vgl-resilience.json")

        config = json.dumps({
            "stuck_threshold": 3,
            "circuit_breaker_threshold": 5,
            "max_vgl_iterations": 50,
            "timeout_hours": 8,
        })
        result = self._run_cli(["--check-all", "1.1", "--config", config], state_path)
        assert result.returncode == 0

    def test_cli_check_all_stuck(self):
        """CLI --check-all exits 1 when stuck."""
        tmp_dir = tempfile.mkdtemp()
        state_path = os.path.join(tmp_dir, "vgl-resilience.json")

        # Record 3 failures
        self._run_cli(["--record-failure", "1.1"], state_path)
        self._run_cli(["--record-failure", "1.1"], state_path)
        self._run_cli(["--record-failure", "1.1"], state_path)

        config = json.dumps({
            "stuck_threshold": 3,
            "circuit_breaker_threshold": 5,
            "max_vgl_iterations": 50,
            "timeout_hours": 8,
        })
        result = self._run_cli(["--check-all", "1.1", "--config", config], state_path)
        assert result.returncode == 1

    def test_cli_reset(self):
        """CLI --reset clears all state."""
        tmp_dir = tempfile.mkdtemp()
        state_path = os.path.join(tmp_dir, "vgl-resilience.json")

        # Record some failures
        self._run_cli(["--record-failure", "1.1"], state_path)
        self._run_cli(["--record-failure", "1.2"], state_path)

        # Reset
        result = self._run_cli(["--reset"], state_path)
        assert result.returncode == 0

        with open(state_path) as f:
            data = json.load(f)
        assert data["task_failures"] == {}
        assert data["total_failures"] == 0

    def test_cli_analyze_failures(self):
        """CLI --analyze-failures outputs JSON analysis."""
        tmp_dir = tempfile.mkdtemp()
        state_path = os.path.join(tmp_dir, "vgl-resilience.json")

        # Record some failures with patterns
        for _ in range(3):
            self._run_cli(["--record-failure", "1.1", "--error", "ImportError: no module"], state_path)

        result = self._run_cli(["--analyze-failures"], state_path)
        assert result.returncode == 0
        analysis = json.loads(result.stdout)
        assert "repeated_errors" in analysis

    def test_cli_check_circuit_breaker(self):
        """CLI --check-circuit-breaker exits correctly."""
        tmp_dir = tempfile.mkdtemp()
        state_path = os.path.join(tmp_dir, "vgl-resilience.json")

        # Record 5 failures across different tasks
        for i in range(5):
            self._run_cli(["--record-failure", f"task-{i}"], state_path)

        result = self._run_cli(["--check-circuit-breaker", "--threshold", "5"], state_path)
        assert result.returncode == 1
        assert "Circuit breaker" in result.stdout or "circuit" in result.stdout.lower()
