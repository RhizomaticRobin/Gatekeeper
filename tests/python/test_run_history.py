"""Tests for run history database (scripts/run_history.py).

Validates:
  - record_outcome writes a JSON entry to .planning/history/runs.jsonl
  - get_history returns all records for a given task_id
  - get_stats computes average iterations, pass rate, and duration
  - History file uses JSONL format (one JSON object per line)
"""

import json
import os
import sys
import time

import pytest

# Allow importing from scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from run_history import record_outcome, get_history, get_all_history, get_stats


@pytest.fixture
def history_dir(tmp_path):
    """Create a temporary history directory and return its path."""
    hdir = tmp_path / ".planning" / "history"
    hdir.mkdir(parents=True)
    return str(hdir)


@pytest.fixture
def history_file(history_dir):
    """Return the path to the runs.jsonl file in the temp history dir."""
    return os.path.join(history_dir, "runs.jsonl")


class TestRecordOutcomeCreatesFile:
    """record_outcome should create the JSONL file on first record."""

    def test_record_outcome_creates_file(self, history_dir, history_file):
        # File should not exist yet
        assert not os.path.exists(history_file)

        record_outcome(
            task_id="1.1",
            iterations=3,
            passed=True,
            duration_seconds=45.2,
            history_dir=history_dir,
        )

        assert os.path.exists(history_file), (
            f"Expected JSONL file at {history_file} after record_outcome"
        )
        # Verify it is valid JSONL (single line, valid JSON)
        with open(history_file, "r") as f:
            lines = f.readlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["task_id"] == "1.1"


class TestRecordOutcomeAppends:
    """Multiple record_outcome calls should produce multiple JSONL lines."""

    def test_record_outcome_appends(self, history_dir, history_file):
        record_outcome("1.1", 2, True, 30.0, history_dir=history_dir)
        record_outcome("1.2", 4, False, 60.0, history_dir=history_dir)
        record_outcome("2.1", 1, True, 15.5, history_dir=history_dir)

        with open(history_file, "r") as f:
            lines = f.readlines()
        assert len(lines) == 3, f"Expected 3 lines, got {len(lines)}"

        # Each line should be valid JSON
        for i, line in enumerate(lines):
            record = json.loads(line.strip())
            assert "task_id" in record, f"Line {i} missing task_id"


class TestGetHistoryFilter:
    """get_history(task_id=...) should return only matching records."""

    def test_get_history_filter(self, history_dir):
        record_outcome("1.1", 2, True, 30.0, history_dir=history_dir)
        record_outcome("1.2", 4, False, 60.0, history_dir=history_dir)
        record_outcome("1.1", 3, True, 25.0, history_dir=history_dir)
        record_outcome("2.1", 1, True, 10.0, history_dir=history_dir)

        results = get_history(task_id="1.1", history_dir=history_dir)

        assert len(results) == 2, f"Expected 2 records for task 1.1, got {len(results)}"
        for r in results:
            assert r["task_id"] == "1.1"


class TestGetHistoryAll:
    """get_history with no filter should return all records."""

    def test_get_history_all(self, history_dir):
        record_outcome("1.1", 2, True, 30.0, history_dir=history_dir)
        record_outcome("1.2", 4, False, 60.0, history_dir=history_dir)
        record_outcome("2.1", 1, True, 10.0, history_dir=history_dir)

        all_records = get_all_history(history_dir=history_dir)

        assert len(all_records) == 3, f"Expected 3 records, got {len(all_records)}"
        task_ids = {r["task_id"] for r in all_records}
        assert task_ids == {"1.1", "1.2", "2.1"}


class TestGetStats:
    """get_stats should compute averages correctly."""

    def test_get_stats(self, history_dir):
        # Two passes, one fail
        record_outcome("1.1", 2, True, 30.0, history_dir=history_dir)
        record_outcome("1.1", 4, False, 60.0, history_dir=history_dir)
        record_outcome("1.1", 3, True, 45.0, history_dir=history_dir)

        stats = get_stats(history_dir=history_dir)

        assert "total_runs" in stats
        assert stats["total_runs"] == 3

        assert "avg_iterations" in stats
        assert abs(stats["avg_iterations"] - 3.0) < 0.01  # (2+4+3)/3

        assert "pass_rate" in stats
        # 2 out of 3 passed
        assert abs(stats["pass_rate"] - (2 / 3)) < 0.01

        assert "avg_duration_s" in stats
        assert abs(stats["avg_duration_s"] - 45.0) < 0.01  # (30+60+45)/3


class TestEmptyHistory:
    """Stats should return zeros for empty history."""

    def test_empty_history(self, history_dir):
        stats = get_stats(history_dir=history_dir)

        assert stats["total_runs"] == 0
        assert stats["avg_iterations"] == 0
        assert stats["pass_rate"] == 0
        assert stats["avg_duration_s"] == 0


class TestRecordFields:
    """All expected fields must be present in a recorded entry."""

    def test_record_fields(self, history_dir, history_file):
        record_outcome(
            task_id="2.1",
            iterations=5,
            passed=False,
            duration_seconds=120.0,
            failure_reasons=["lint error", "test timeout"],
            session_id="sess-abc-123",
            history_dir=history_dir,
        )

        with open(history_file, "r") as f:
            record = json.loads(f.readline())

        required_fields = {
            "task_id", "iterations", "passed", "duration_s",
            "failure_reasons", "session_id", "timestamp"
        }
        for field in required_fields:
            assert field in record, f"Missing field: {field}"

        assert record["task_id"] == "2.1"
        assert record["iterations"] == 5
        assert record["passed"] is False
        assert record["duration_s"] == 120.0
        assert record["failure_reasons"] == ["lint error", "test timeout"]
        assert record["session_id"] == "sess-abc-123"


class TestTimestampAuto:
    """timestamp should be added automatically as an ISO-format string."""

    def test_timestamp_auto(self, history_dir, history_file):
        before = time.time()
        record_outcome("1.1", 1, True, 10.0, history_dir=history_dir)
        after = time.time()

        with open(history_file, "r") as f:
            record = json.loads(f.readline())

        assert "timestamp" in record
        # Timestamp should be a string (ISO format)
        ts = record["timestamp"]
        assert isinstance(ts, str), f"timestamp should be str, got {type(ts)}"
        # Should be parseable and roughly in the right time range
        from datetime import datetime
        parsed = datetime.fromisoformat(ts)
        assert before <= parsed.timestamp() <= after + 1, (
            f"Timestamp {ts} not in expected range [{before}, {after}]"
        )
