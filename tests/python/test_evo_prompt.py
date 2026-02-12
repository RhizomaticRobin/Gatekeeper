"""Tests for scripts/evo_prompt.py — Evolution Prompt Builder.

Tests the EvolutionPromptBuilder which samples from the evolution population
database and constructs rich markdown prompts with 5 sections:
  1. Evolution Context
  2. Parent Approach
  3. What Went Wrong
  4. Inspiration Approaches
  5. Your Directive
"""

import json
import os
import random
import subprocess
import sys
import time
import uuid

import pytest

# Import from scripts/ (conftest.py ensures scripts/ is on sys.path)
from evo_db import Approach, EvolutionDB
from evo_prompt import EvolutionPromptBuilder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_approach(
    island=0,
    test_pass_rate=0.8,
    complexity=5.0,
    generation=0,
    task_id="1.1",
    prompt_addendum="Try a modular approach",
    parent_id=None,
    iteration=0,
    artifacts=None,
    **extra_metrics,
):
    """Create an Approach with sensible defaults for testing."""
    metrics = {"test_pass_rate": test_pass_rate, "complexity": complexity}
    metrics.update(extra_metrics)
    return Approach(
        id=str(uuid.uuid4()),
        prompt_addendum=prompt_addendum,
        parent_id=parent_id,
        generation=generation,
        metrics=metrics,
        island=island,
        feature_coords=(),
        task_id=task_id,
        task_type="backend",
        file_patterns=["scripts/*.py"],
        artifacts=artifacts if artifacts is not None else {},
        timestamp=time.time(),
        iteration=iteration,
    )


def _populate_db(db_path, num_per_island=3, num_islands=3, task_id="1.1"):
    """Create and save a populated EvolutionDB.

    Returns the EvolutionDB instance and the list of approaches that were added.
    """
    db = EvolutionDB(config={"num_islands": num_islands})
    approaches = []
    for isl in range(num_islands):
        for i in range(num_per_island):
            a = _make_approach(
                island=isl,
                test_pass_rate=0.3 + i * 0.2,
                complexity=2.0 + i,
                generation=i,
                task_id=task_id,
                prompt_addendum=f"Strategy island={isl} gen={i}: use approach variant {i}",
                artifacts={
                    "test_output": f"PASSED {i+1}/5 tests on island {isl}",
                    "error_trace": f"Traceback: error in step {i} on island {isl}",
                },
            )
            db.add(a)
            approaches.append(a)
    db.save(db_path)
    return db, approaches


# ---------------------------------------------------------------------------
# T1  test_build_prompt_with_population
# ---------------------------------------------------------------------------

class TestBuildPromptWithPopulation:
    def test_build_prompt_with_population(self, tmp_path):
        """build_prompt() produces markdown with all 5 required sections
        when the population is non-empty."""
        db_path = str(tmp_path / "evo_db")
        _populate_db(db_path)

        builder = EvolutionPromptBuilder()
        prompt = builder.build_prompt(db_path=db_path, task_id="1.1")

        # Must be a non-empty string
        assert isinstance(prompt, str)
        assert len(prompt) > 100

        # All 5 section headers must be present (case-insensitive check)
        lower = prompt.lower()
        assert "evolution context" in lower, "Missing 'Evolution Context' section"
        assert "parent approach" in lower, "Missing 'Parent Approach' section"
        assert "what went wrong" in lower, "Missing 'What Went Wrong' section"
        assert "inspiration" in lower, "Missing 'Inspiration Approaches' section"
        assert "directive" in lower, "Missing 'Your Directive' section"


# ---------------------------------------------------------------------------
# T2  test_build_prompt_empty_population
# ---------------------------------------------------------------------------

class TestBuildPromptEmptyPopulation:
    def test_build_prompt_empty_population(self, tmp_path):
        """build_prompt() on an empty database produces a graceful minimal
        prompt without crashing."""
        db_path = str(tmp_path / "empty_evo_db")
        db = EvolutionDB()
        db.save(db_path)

        builder = EvolutionPromptBuilder()
        prompt = builder.build_prompt(db_path=db_path, task_id="1.1")

        # Should return something (not crash)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

        # Should not contain error tracebacks
        assert "Traceback" not in prompt or "error_trace" in prompt.lower()


# ---------------------------------------------------------------------------
# T3  test_parent_section_includes_metrics
# ---------------------------------------------------------------------------

class TestParentSectionIncludesMetrics:
    def test_parent_section_includes_metrics(self, tmp_path):
        """The 'Parent Approach' section includes metrics (test_pass_rate)
        and prompt_addendum from the sampled parent."""
        db_path = str(tmp_path / "evo_db")
        _populate_db(db_path, num_per_island=3)

        builder = EvolutionPromptBuilder()
        prompt = builder.build_prompt(db_path=db_path, task_id="1.1")

        # Must mention test_pass_rate somewhere
        assert "test_pass_rate" in prompt, "Prompt should include parent metrics"

        # Must include prompt_addendum text (some approach strategy)
        # At least one of the strategy patterns should appear
        assert "Strategy" in prompt or "approach" in prompt.lower(), (
            "Prompt should include parent prompt_addendum"
        )


# ---------------------------------------------------------------------------
# T4  test_inspiration_from_different_islands
# ---------------------------------------------------------------------------

class TestInspirationFromDifferentIslands:
    def test_inspiration_from_different_islands(self, tmp_path):
        """Inspiration approaches come from different islands than the parent.

        We populate 3 islands and request island_id=0. The inspiration section
        should reference approaches from island 1 or 2 (not 0).
        """
        db_path = str(tmp_path / "evo_db")
        _populate_db(db_path, num_per_island=3, num_islands=3)

        builder = EvolutionPromptBuilder(config={"num_inspirations": 2})
        prompt = builder.build_prompt(db_path=db_path, task_id="1.1", island_id=0)

        # The prompt should contain inspiration content
        lower = prompt.lower()
        assert "inspiration" in lower

        # Inspiration section should reference islands other than 0
        # Since our approach prompt_addendum patterns include "island=N",
        # the inspiration section should contain "island=1" or "island=2"
        insp_start = lower.find("inspiration")
        if insp_start >= 0:
            insp_section = prompt[insp_start:]
            # Should have approaches from other islands
            has_other_island = ("island=1" in insp_section or "island=2" in insp_section)
            assert has_other_island, (
                "Inspiration section should contain approaches from islands other than 0"
            )


# ---------------------------------------------------------------------------
# T5  test_artifacts_truncated
# ---------------------------------------------------------------------------

class TestArtifactsTruncated:
    def test_artifacts_truncated(self, tmp_path):
        """Artifacts (error traces, test output) are included but truncated
        to max_artifact_chars."""
        db_path = str(tmp_path / "evo_db")
        db = EvolutionDB()
        # Create a single approach with a very long artifact
        long_artifact = "X" * 2000
        a = _make_approach(
            island=0,
            test_pass_rate=0.5,
            task_id="1.1",
            artifacts={"error_trace": long_artifact, "test_output": "ok"},
        )
        db.add(a)
        db.save(db_path)

        max_chars = 500
        builder = EvolutionPromptBuilder(config={"max_artifact_chars": max_chars})
        prompt = builder.build_prompt(db_path=db_path, task_id="1.1")

        # The full 2000-char artifact should NOT appear untruncated
        assert long_artifact not in prompt, "Full artifact should be truncated"

        # Some portion of the artifact should still be present (truncated version)
        # The builder should include at least some X characters
        assert "X" * min(100, max_chars) in prompt or "truncat" in prompt.lower(), (
            "Artifact content should be present (truncated)"
        )


# ---------------------------------------------------------------------------
# T6  test_directive_varies
# ---------------------------------------------------------------------------

class TestDirectiveVaries:
    def test_directive_varies(self, tmp_path):
        """The evolution directive varies across different generations,
        preventing repetitive prompts."""
        db_path = str(tmp_path / "evo_db")
        _populate_db(db_path, num_per_island=5)

        builder = EvolutionPromptBuilder()

        # Build prompts using different generation seed offsets
        directives = set()
        for gen in range(10):
            directive = builder._select_directive(generation=gen)
            directives.add(directive)

        # At least 3 different directives should be produced across 10 generations
        assert len(directives) >= 3, (
            f"Expected at least 3 different directives, got {len(directives)}: {directives}"
        )


# ---------------------------------------------------------------------------
# T7  test_format_approach
# ---------------------------------------------------------------------------

class TestFormatApproach:
    def test_format_approach(self):
        """format_approach() produces a readable markdown block for an approach."""
        builder = EvolutionPromptBuilder()
        approach = _make_approach(
            island=1,
            test_pass_rate=0.75,
            complexity=3.0,
            generation=2,
            prompt_addendum="Use dependency injection for testability",
            artifacts={"test_output": "3/4 passed"},
        )
        formatted = builder.format_approach(approach)

        assert isinstance(formatted, str)
        assert len(formatted) > 0

        # Should include the prompt addendum
        assert "dependency injection" in formatted.lower()

        # Should include metrics
        assert "test_pass_rate" in formatted or "0.75" in formatted

        # Should include island info or generation
        assert "island" in formatted.lower() or str(approach.generation) in formatted


# ---------------------------------------------------------------------------
# T8  test_cli_build
# ---------------------------------------------------------------------------

class TestCliBuild:
    def test_cli_build(self, tmp_path):
        """CLI: python3 evo_prompt.py --build DB_PATH TASK_ID produces output."""
        db_path = str(tmp_path / "evo_db")
        _populate_db(db_path)

        script_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "scripts", "evo_prompt.py"
        )
        script_path = os.path.abspath(script_path)

        result = subprocess.run(
            [sys.executable, script_path, "--build", db_path, "1.1"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        output = result.stdout
        assert len(output) > 50, "CLI should produce substantial output"

        # Output should contain section markers
        lower = output.lower()
        assert "evolution context" in lower or "parent" in lower, (
            "CLI output should contain prompt sections"
        )

    def test_cli_build_with_island(self, tmp_path):
        """CLI: python3 evo_prompt.py --build DB_PATH TASK_ID --island 1 works."""
        db_path = str(tmp_path / "evo_db")
        _populate_db(db_path)

        script_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "scripts", "evo_prompt.py"
        )
        script_path = os.path.abspath(script_path)

        result = subprocess.run(
            [sys.executable, script_path, "--build", db_path, "1.1", "--island", "1"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, f"CLI with --island failed: {result.stderr}"
        assert len(result.stdout) > 50


# ---------------------------------------------------------------------------
# T9  test_build_prompt_single_island
# ---------------------------------------------------------------------------

class TestBuildPromptSingleIsland:
    def test_build_prompt_single_island(self, tmp_path):
        """build_prompt() works when all approaches are on a single island
        (no cross-island inspirations available)."""
        db_path = str(tmp_path / "single_island_db")
        db = EvolutionDB(config={"num_islands": 1})
        for i in range(3):
            a = _make_approach(
                island=0,
                test_pass_rate=0.3 + i * 0.2,
                generation=i,
                task_id="1.1",
                prompt_addendum=f"Single island strategy gen={i}",
            )
            db.add(a)
        db.save(db_path)

        builder = EvolutionPromptBuilder()
        prompt = builder.build_prompt(db_path=db_path, task_id="1.1", island_id=0)

        # Should still produce a valid prompt
        assert isinstance(prompt, str)
        assert len(prompt) > 50

        # Should have parent section
        assert "parent" in prompt.lower()

        # Inspiration section should be minimal or note no cross-island available
        # But should not crash
