"""Tests for scripts/learnings.py — Learnings Accumulator.

TDD-first tests for:
  - extract_learning: parse verifier feedback into structured learning entries
  - store_learning: append to .planning/learnings.jsonl
  - get_learnings: list all, optionally filtered by task_type
  - get_relevant_learnings: match by file patterns and task type
"""

import sys
import os
import json
import pytest

# Allow importing from scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from learnings import (
    extract_learning,
    store_learning,
    get_learnings,
    get_relevant_learnings,
)


class TestExtractLearningFromFailure:
    """test_extract_learning_from_failure — parse failure feedback into learning."""

    def test_basic_extraction(self):
        result = extract_learning(
            task_id="1.1",
            verifier_feedback="Test failed because the auth middleware was not applied. Fixed by adding auth check to route handler in src/routes/auth.ts",
            outcome="fail",
        )
        assert result["task_id"] == "1.1"
        assert "description" in result
        assert result["description"]  # non-empty
        assert "category" in result
        assert result["category"] in (
            "fix_pattern",
            "test_pattern",
            "dependency",
            "configuration",
            "approach",
        )
        assert "file_patterns" in result
        assert isinstance(result["file_patterns"], list)
        assert "task_type" in result
        assert "timestamp" in result

    def test_extracts_file_patterns_from_feedback(self):
        result = extract_learning(
            task_id="2.1",
            verifier_feedback="The issue was in src/components/Header.tsx — missing import. Fixed by updating src/utils/helpers.ts",
            outcome="fail",
        )
        # Should extract file paths mentioned in the feedback
        patterns = result["file_patterns"]
        assert any("Header" in p or "src/components" in p for p in patterns)
        assert any("helpers" in p or "src/utils" in p for p in patterns)

    def test_outcome_stored(self):
        result = extract_learning(
            task_id="3.1",
            verifier_feedback="All tests passed on first try.",
            outcome="pass",
        )
        assert result["task_id"] == "3.1"
        assert "timestamp" in result


class TestStoreLearningCreatesFile:
    """test_store_learning_creates_file — JSONL created on first store."""

    def test_creates_file_on_first_store(self, tmp_path):
        jsonl_path = tmp_path / "learnings.jsonl"
        learning = {
            "task_id": "1.1",
            "category": "fix_pattern",
            "description": "Auth middleware must be applied before route handlers",
            "file_patterns": ["src/routes/*.ts"],
            "task_type": "backend",
            "timestamp": "2025-01-01T00:00:00",
        }
        store_learning(learning, storage_path=str(jsonl_path))
        assert jsonl_path.exists()
        lines = jsonl_path.read_text().strip().split("\n")
        assert len(lines) == 1
        stored = json.loads(lines[0])
        assert stored["task_id"] == "1.1"
        assert stored["category"] == "fix_pattern"

    def test_appends_to_existing_file(self, tmp_path):
        jsonl_path = tmp_path / "learnings.jsonl"
        learning1 = {
            "task_id": "1.1",
            "category": "fix_pattern",
            "description": "First learning",
            "file_patterns": [],
            "task_type": "backend",
            "timestamp": "2025-01-01T00:00:00",
        }
        learning2 = {
            "task_id": "1.2",
            "category": "test_pattern",
            "description": "Second learning",
            "file_patterns": [],
            "task_type": "frontend",
            "timestamp": "2025-01-01T00:01:00",
        }
        store_learning(learning1, storage_path=str(jsonl_path))
        store_learning(learning2, storage_path=str(jsonl_path))
        lines = jsonl_path.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["task_id"] == "1.1"
        assert json.loads(lines[1])["task_id"] == "1.2"

    def test_creates_parent_directory(self, tmp_path):
        jsonl_path = tmp_path / "subdir" / "learnings.jsonl"
        learning = {
            "task_id": "1.1",
            "category": "approach",
            "description": "Test learning",
            "file_patterns": [],
            "task_type": "backend",
            "timestamp": "2025-01-01T00:00:00",
        }
        store_learning(learning, storage_path=str(jsonl_path))
        assert jsonl_path.exists()


class TestGetLearningsFilter:
    """test_get_learnings_filter — filter by task_type."""

    def _populate(self, path):
        learnings = [
            {
                "task_id": "1.1",
                "category": "fix_pattern",
                "description": "Backend fix",
                "file_patterns": ["src/api/*.py"],
                "task_type": "backend",
                "timestamp": "2025-01-01T00:00:00",
            },
            {
                "task_id": "1.2",
                "category": "test_pattern",
                "description": "Frontend pattern",
                "file_patterns": ["src/components/*.tsx"],
                "task_type": "frontend",
                "timestamp": "2025-01-01T00:01:00",
            },
            {
                "task_id": "2.1",
                "category": "configuration",
                "description": "Another backend config",
                "file_patterns": ["config/*.yaml"],
                "task_type": "backend",
                "timestamp": "2025-01-01T00:02:00",
            },
        ]
        for l in learnings:
            store_learning(l, storage_path=str(path))

    def test_get_all_learnings(self, tmp_path):
        jsonl_path = tmp_path / "learnings.jsonl"
        self._populate(jsonl_path)
        all_learnings = get_learnings(storage_path=str(jsonl_path))
        assert len(all_learnings) == 3

    def test_filter_by_task_type(self, tmp_path):
        jsonl_path = tmp_path / "learnings.jsonl"
        self._populate(jsonl_path)
        backend = get_learnings(task_type="backend", storage_path=str(jsonl_path))
        assert len(backend) == 2
        assert all(l["task_type"] == "backend" for l in backend)

    def test_filter_returns_empty_for_no_match(self, tmp_path):
        jsonl_path = tmp_path / "learnings.jsonl"
        self._populate(jsonl_path)
        result = get_learnings(task_type="devops", storage_path=str(jsonl_path))
        assert result == []

    def test_get_learnings_no_file(self, tmp_path):
        jsonl_path = tmp_path / "nonexistent.jsonl"
        result = get_learnings(storage_path=str(jsonl_path))
        assert result == []


class TestGetRelevantLearnings:
    """test_get_relevant_learnings — match by file patterns."""

    def _populate(self, path):
        learnings = [
            {
                "task_id": "1.1",
                "category": "fix_pattern",
                "description": "Auth route fix",
                "file_patterns": ["src/routes/auth.ts", "src/middleware/auth.ts"],
                "task_type": "backend",
                "timestamp": "2025-01-01T00:00:00",
            },
            {
                "task_id": "1.2",
                "category": "test_pattern",
                "description": "Component render pattern",
                "file_patterns": ["src/components/Header.tsx"],
                "task_type": "frontend",
                "timestamp": "2025-01-01T00:01:00",
            },
            {
                "task_id": "2.1",
                "category": "dependency",
                "description": "Database connection config",
                "file_patterns": ["src/db/connection.py", "config/database.yaml"],
                "task_type": "backend",
                "timestamp": "2025-01-01T00:02:00",
            },
        ]
        for l in learnings:
            store_learning(l, storage_path=str(path))

    def test_match_by_file_pattern(self, tmp_path):
        jsonl_path = tmp_path / "learnings.jsonl"
        self._populate(jsonl_path)
        context = {
            "file_patterns": ["src/routes/auth.ts", "src/routes/users.ts"],
            "task_type": "backend",
        }
        relevant = get_relevant_learnings(context, storage_path=str(jsonl_path))
        assert len(relevant) >= 1
        # The auth route learning should be most relevant
        descriptions = [r["description"] for r in relevant]
        assert "Auth route fix" in descriptions

    def test_match_by_task_type(self, tmp_path):
        jsonl_path = tmp_path / "learnings.jsonl"
        self._populate(jsonl_path)
        context = {
            "file_patterns": ["src/db/connection.py"],
            "task_type": "backend",
        }
        relevant = get_relevant_learnings(context, storage_path=str(jsonl_path))
        # Should match the database learning by file pattern AND task_type
        assert len(relevant) >= 1
        descriptions = [r["description"] for r in relevant]
        assert "Database connection config" in descriptions

    def test_match_by_partial_path_overlap(self, tmp_path):
        jsonl_path = tmp_path / "learnings.jsonl"
        self._populate(jsonl_path)
        context = {
            "file_patterns": ["src/components/Footer.tsx"],
            "task_type": "frontend",
        }
        relevant = get_relevant_learnings(context, storage_path=str(jsonl_path))
        # Should match Header.tsx learning because of shared directory pattern
        assert len(relevant) >= 1
        descriptions = [r["description"] for r in relevant]
        assert "Component render pattern" in descriptions


class TestRelevantEmpty:
    """test_relevant_empty — no matches returns empty list."""

    def test_no_learnings_file(self, tmp_path):
        jsonl_path = tmp_path / "nonexistent.jsonl"
        context = {
            "file_patterns": ["src/anything.ts"],
            "task_type": "backend",
        }
        result = get_relevant_learnings(context, storage_path=str(jsonl_path))
        assert result == []

    def test_no_matching_context(self, tmp_path):
        jsonl_path = tmp_path / "learnings.jsonl"
        learning = {
            "task_id": "1.1",
            "category": "fix_pattern",
            "description": "Specific fix for module X",
            "file_patterns": ["src/module_x/specific.py"],
            "task_type": "backend",
            "timestamp": "2025-01-01T00:00:00",
        }
        store_learning(learning, storage_path=str(jsonl_path))
        context = {
            "file_patterns": ["totally/different/path.rs"],
            "task_type": "devops",
        }
        result = get_relevant_learnings(context, storage_path=str(jsonl_path))
        assert result == []

    def test_empty_context(self, tmp_path):
        jsonl_path = tmp_path / "learnings.jsonl"
        learning = {
            "task_id": "1.1",
            "category": "fix_pattern",
            "description": "Some fix",
            "file_patterns": ["src/a.py"],
            "task_type": "backend",
            "timestamp": "2025-01-01T00:00:00",
        }
        store_learning(learning, storage_path=str(jsonl_path))
        context = {"file_patterns": [], "task_type": ""}
        result = get_relevant_learnings(context, storage_path=str(jsonl_path))
        assert result == []


class TestExtractCategories:
    """test_extract_categories — different feedback patterns produce different categories."""

    def test_fix_pattern_category(self):
        result = extract_learning(
            task_id="1.1",
            verifier_feedback="The test failed. Fixed by adding null check in src/utils.ts",
            outcome="fail",
        )
        assert result["category"] == "fix_pattern"

    def test_test_pattern_category(self):
        result = extract_learning(
            task_id="1.2",
            verifier_feedback="Test was flaky because of async timing. The test needs a waitFor assertion instead of immediate check.",
            outcome="fail",
        )
        assert result["category"] == "test_pattern"

    def test_dependency_category(self):
        result = extract_learning(
            task_id="2.1",
            verifier_feedback="Build failed due to missing dependency. Need to install package @types/node. Import was missing.",
            outcome="fail",
        )
        assert result["category"] == "dependency"

    def test_configuration_category(self):
        result = extract_learning(
            task_id="2.2",
            verifier_feedback="Environment variable DATABASE_URL was not set in .env config. Configuration file was missing the entry.",
            outcome="fail",
        )
        assert result["category"] == "configuration"

    def test_approach_category_fallback(self):
        result = extract_learning(
            task_id="3.1",
            verifier_feedback="The implementation approach was wrong. Should have used a different algorithm for sorting.",
            outcome="fail",
        )
        assert result["category"] == "approach"
