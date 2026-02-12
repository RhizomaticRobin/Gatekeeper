#!/usr/bin/env python3
"""Evolution Prompt Builder for GSD-VGL.

Samples from the evolution population database (evo_db.py) and constructs
rich markdown prompts with 5 sections for guiding the executor agent:

  1. Evolution Context   — generation, population stats
  2. Parent Approach     — sampled parent's strategy, metrics, artifacts
  3. What Went Wrong     — failure artifacts (error traces, test output)
  4. Inspiration Approaches — cross-island strategies for diversity
  5. Your Directive      — varied evolution instruction

Classes:
    EvolutionPromptBuilder — builds evolution context prompts from population data

CLI:
    python3 evo_prompt.py --build DB_PATH TASK_ID [--island N]

References:
    - scripts/evo_db.py: Approach, EvolutionDB
    - openevolve/prompt/sampler.py: prompt construction patterns
"""

import argparse
import os
import random
import sys
from typing import Any, Dict, List, Optional

# Ensure scripts/ is importable
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from evo_db import Approach, EvolutionDB


# ---------------------------------------------------------------------------
# Directive variations
# ---------------------------------------------------------------------------

_DEFAULT_DIRECTIVE_VARIATIONS = [
    (
        "Your parent achieved a test pass rate of {score:.1%}. "
        "Analyze what worked and what didn't, then propose a REFINED strategy "
        "that pushes the pass rate higher. Focus on the failing test cases."
    ),
    (
        "The current approach passes {percent:.0f}% of tests. "
        "Take a step back and consider a fundamentally different angle — "
        "sometimes incremental fixes aren't enough. Be bold."
    ),
    (
        "With {score:.1%} test pass rate, you're making progress but not there yet. "
        "Identify the root cause of remaining failures and fix the underlying issue, "
        "not just the symptoms."
    ),
    (
        "The parent strategy reached {percent:.0f}% passing. "
        "Study the inspiration approaches from other islands for fresh ideas. "
        "Combine the best elements into a hybrid strategy."
    ),
    (
        "At {score:.1%} pass rate, focus on robustness. "
        "Make sure edge cases are handled, error paths are covered, and the "
        "approach degrades gracefully. Quality over cleverness."
    ),
    (
        "Current score: {percent:.0f}%. Think about what assumptions the parent "
        "strategy made that might be wrong. Challenge those assumptions and "
        "try an approach that doesn't rely on them."
    ),
    (
        "The parent hit {score:.1%}. Rather than changing everything, find the "
        "single most impactful improvement you can make. Small, targeted changes "
        "often beat large rewrites."
    ),
]


# ---------------------------------------------------------------------------
# EvolutionPromptBuilder
# ---------------------------------------------------------------------------

class EvolutionPromptBuilder:
    """Builds evolution context prompts from the population database.

    Parameters (via config dict):
        num_inspirations    — number of cross-island inspiration approaches (default 2)
        max_artifact_chars  — max characters per artifact before truncation (default 500)
        directive_variations — list of directive template strings (default: 7 built-in)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.num_inspirations: int = cfg.get("num_inspirations", 2)
        self.max_artifact_chars: int = cfg.get("max_artifact_chars", 500)
        self.directive_variations: List[str] = cfg.get(
            "directive_variations", list(_DEFAULT_DIRECTIVE_VARIATIONS)
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_prompt(
        self,
        db_path: str,
        task_id: str,
        island_id: Optional[int] = None,
    ) -> str:
        """Load the EvolutionDB and build a 5-section markdown prompt.

        Sections:
            1. Evolution Context
            2. Parent Approach
            3. What Went Wrong
            4. Inspiration Approaches
            5. Your Directive

        Args:
            db_path: Path to the EvolutionDB directory.
            task_id: Task ID to filter approaches.
            island_id: Island to sample from (default: random).

        Returns:
            Markdown string with all 5 sections.
        """
        db = EvolutionDB()
        db.load(db_path)

        # Determine island
        if island_id is None:
            island_id = random.randint(0, max(db.num_islands - 1, 0))

        # Try to sample parent + inspirations
        sample_result = db.sample(
            island_id=island_id,
            num_inspirations=self.num_inspirations,
        )

        # If the chosen island is empty, try all other islands before giving up
        if sample_result is None:
            islands_to_try = list(range(db.num_islands))
            random.shuffle(islands_to_try)
            for alt_island in islands_to_try:
                if alt_island == island_id:
                    continue
                sample_result = db.sample(
                    island_id=alt_island,
                    num_inspirations=self.num_inspirations,
                )
                if sample_result is not None:
                    island_id = alt_island
                    break

        if sample_result is None:
            return self._build_empty_prompt(task_id)

        parent, inspirations = sample_result
        return self._build_full_prompt(db, parent, inspirations, task_id)

    def format_approach(self, approach: Approach) -> str:
        """Format a single approach as a readable markdown block.

        Args:
            approach: The Approach to format.

        Returns:
            Markdown string describing the approach.
        """
        lines = []
        lines.append(f"**Strategy** (island={approach.island}, generation={approach.generation}):")
        lines.append("")
        lines.append(f"> {approach.prompt_addendum}")
        lines.append("")

        # Metrics
        lines.append("**Metrics:**")
        for key, val in approach.metrics.items():
            if isinstance(val, float):
                lines.append(f"- {key}: {val:.4f}")
            else:
                lines.append(f"- {key}: {val}")

        # Artifacts (brief)
        if approach.artifacts:
            lines.append("")
            lines.append("**Artifacts:**")
            for akey, aval in approach.artifacts.items():
                snippet = str(aval)[:200]
                if len(str(aval)) > 200:
                    snippet += "..."
                lines.append(f"- {akey}: {snippet}")

        return "\n".join(lines)

    def _select_directive(self, generation: int) -> str:
        """Select a directive variation using generation as a seed offset.

        Args:
            generation: The evolution generation number.

        Returns:
            A directive template string (with {score} and {percent} placeholders).
        """
        idx = generation % len(self.directive_variations)
        return self.directive_variations[idx]

    # ------------------------------------------------------------------
    # Internal: build full prompt
    # ------------------------------------------------------------------

    def _build_full_prompt(
        self,
        db: EvolutionDB,
        parent: Approach,
        inspirations: List[Approach],
        task_id: str,
    ) -> str:
        """Build the full 5-section markdown prompt."""
        sections = []

        # --- Section 1: Evolution Context ---
        sections.append(self._section_evolution_context(db, parent, task_id))

        # --- Section 2: Parent Approach ---
        sections.append(self._section_parent_approach(parent))

        # --- Section 3: What Went Wrong ---
        sections.append(self._section_what_went_wrong(parent))

        # --- Section 4: Inspiration Approaches ---
        sections.append(self._section_inspirations(inspirations))

        # --- Section 5: Your Directive ---
        sections.append(self._section_directive(parent))

        return "\n\n".join(sections)

    def _section_evolution_context(
        self, db: EvolutionDB, parent: Approach, task_id: str
    ) -> str:
        """Section 1: Evolution Context."""
        stats = db.stats()
        lines = [
            "## Evolution Context",
            "",
            f"- **Task:** {task_id}",
            f"- **Population size:** {stats['population_size']}",
            f"- **Number of islands:** {stats['num_islands']}",
            f"- **Parent island:** {parent.island}",
            f"- **Parent generation:** {parent.generation}",
        ]
        best_score = stats.get("best_score")
        if best_score is not None:
            lines.append(f"- **Best score (global):** {best_score:.4f}")
        return "\n".join(lines)

    def _section_parent_approach(self, parent: Approach) -> str:
        """Section 2: Parent Approach."""
        lines = [
            "## Parent Approach",
            "",
            self.format_approach(parent),
        ]
        return "\n".join(lines)

    def _section_what_went_wrong(self, parent: Approach) -> str:
        """Section 3: What Went Wrong — include artifacts with truncation."""
        lines = [
            "## What Went Wrong",
            "",
        ]

        if not parent.artifacts:
            lines.append("_No failure artifacts recorded for this approach._")
            return "\n".join(lines)

        for key, value in parent.artifacts.items():
            content = str(value)
            if len(content) > self.max_artifact_chars:
                content = content[: self.max_artifact_chars] + "\n... (truncated)"
            lines.append(f"### {key}")
            lines.append(f"```")
            lines.append(content)
            lines.append(f"```")
            lines.append("")

        return "\n".join(lines)

    def _section_inspirations(self, inspirations: List[Approach]) -> str:
        """Section 4: Inspiration Approaches from different islands."""
        lines = [
            "## Inspiration Approaches",
            "",
        ]

        if not inspirations:
            lines.append(
                "_No cross-island inspirations available (single island population)._"
            )
            return "\n".join(lines)

        lines.append(
            "These approaches come from **different islands** and may offer "
            "alternative strategies worth incorporating:"
        )
        lines.append("")

        for i, insp in enumerate(inspirations, 1):
            lines.append(f"### Inspiration {i}")
            lines.append("")
            lines.append(self.format_approach(insp))
            lines.append("")

        return "\n".join(lines)

    def _section_directive(self, parent: Approach) -> str:
        """Section 5: Your Directive — varied instruction for the executor."""
        score = parent.metrics.get("test_pass_rate", 0.0)
        percent = score * 100.0

        template = self._select_directive(parent.generation)
        directive_text = template.format(score=score, percent=percent)

        lines = [
            "## Your Directive",
            "",
            directive_text,
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal: build empty prompt
    # ------------------------------------------------------------------

    def _build_empty_prompt(self, task_id: str) -> str:
        """Build a minimal prompt when the population is empty."""
        return (
            "## Evolution Context\n\n"
            f"- **Task:** {task_id}\n"
            "- **Population:** empty (no prior approaches)\n\n"
            "## Parent Approach\n\n"
            "_No parent approach available. This is the first generation._\n\n"
            "## What Went Wrong\n\n"
            "_No prior attempts to analyze._\n\n"
            "## Inspiration Approaches\n\n"
            "_No inspirations available yet._\n\n"
            "## Your Directive\n\n"
            "You are the first to attempt this task. Start with a clear, "
            "well-structured approach. Focus on correctness first, then optimize."
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="GSD-VGL Evolution Prompt Builder"
    )

    parser.add_argument(
        "--build",
        nargs=2,
        metavar=("DB_PATH", "TASK_ID"),
        help="Build an evolution prompt from DB_PATH for TASK_ID",
    )
    parser.add_argument(
        "--island",
        type=int,
        default=None,
        help="Island ID to sample from (default: random)",
    )

    args = parser.parse_args()

    if args.build:
        db_path, task_id = args.build
        builder = EvolutionPromptBuilder()
        prompt = builder.build_prompt(
            db_path=db_path,
            task_id=task_id,
            island_id=args.island,
        )
        print(prompt)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
