# Task 1.3: Prompt Evolution Builder

## Goal (from must_haves)
**Truths:**
- EvolutionPromptBuilder.build_prompt() produces a markdown document with 5 sections: Evolution Context, Parent Approach, What Went Wrong, Inspiration Approaches, Your Directive
- Parent approach is sampled from evo_db with its metrics and prompt_addendum
- Inspirations are sampled from DIFFERENT islands than the parent
- Artifacts (error traces, test output) are included but truncated to max_artifact_chars
- Directive varies randomly across generations to prevent repetition
- Empty populations produce a graceful minimal prompt (no crash)

**Artifacts:**
- scripts/evo_prompt.py
- tests/python/test_evo_prompt.py

## Context
This is the prompt construction component of the evolutionary intelligence system. It translates the population state (from evo_db.py) into rich evolution context that guides the executor agent (Claude) to generate improved approaches.

The key insight from OpenEvolve's PromptSampler (see /home/user/openevolve/openevolve/prompt/sampler.py) is that effective prompts include: the parent solution with metrics, what went wrong (artifacts), inspiration from diverse alternatives, and a stochastic directive to prevent convergence. Claude naturally "mutates" when given this context -- it synthesizes improvements from the parent, learns from errors, and draws ideas from cross-island inspirations.

The "program" being evolved is the prompt_addendum -- a strategy/approach description that gets prepended to the task prompt. The evolution builder constructs the context that helps Claude produce better addendums each iteration.

## Backend Deliverables
Create `scripts/evo_prompt.py`:

### EvolutionPromptBuilder Class
```python
class EvolutionPromptBuilder:
    def __init__(self, config=None):
        # Defaults: num_inspirations=2, max_artifact_chars=500
        # directive_variations: list of 5+ evolution directives (see below)

    def build_prompt(self, db_path: str, task_id: str, island_id: int = None) -> str:
        # 1. Load EvolutionDB from db_path
        # 2. If island_id not specified, use island 0
        # 3. Sample parent + inspirations via db.sample(island_id)
        # 4. If population empty: return minimal "No prior approaches" context
        # 5. Build 5-section markdown document:
        #
        # ## Evolution Context
        # Generation: {parent.generation + 1}
        # Island: {island_id} of {num_islands}
        # Population: {total_approaches} approaches across {num_islands} islands
        # Best score: {best.metrics.test_pass_rate}
        #
        # ## Parent Approach (Best So Far)
        # **Score:** {parent.metrics.test_pass_rate}
        # **Generation:** {parent.generation}
        # **Island:** {parent.island}
        # ```
        # {parent.prompt_addendum}
        # ```
        #
        # ## What Went Wrong
        # {parent.artifacts.error_trace, truncated to max_artifact_chars}
        # {parent.artifacts.test_output, truncated to max_artifact_chars}
        #
        # ## Inspiration Approaches
        # For each inspiration:
        #   **Score:** {insp.metrics.test_pass_rate} (Island {insp.island})
        #   ```
        #   {insp.prompt_addendum}
        #   ```
        #
        # ## Your Directive
        # {randomly selected directive}

    def format_approach(self, approach) -> str:
        # Format single approach as markdown block with score, generation, island, addendum

    def _select_directive(self, generation: int) -> str:
        # Select directive with variation to prevent repetition
        # Use generation as seed offset for deterministic but varying selection
        # Return one of the directive_variations
```

### Directive Variations
```python
DIRECTIVE_VARIATIONS = [
    "Generate a NEW approach that fixes the issues above while building on the parent's strengths.",
    "The parent approach scored {score}. Improve it by addressing the failures and drawing inspiration from alternative approaches.",
    "Study the inspiration approaches for ideas the parent missed. Synthesize a better strategy.",
    "Focus on the errors above. What pattern of mistakes is emerging? Break the pattern with a fundamentally different strategy.",
    "The parent is {percent}% there. Refine the working parts, replace the broken parts.",
]
```
Note: `{score}` and `{percent}` are filled from parent metrics at format time (test_pass_rate and test_pass_rate*100 respectively).

### CLI Interface
```bash
python3 evo_prompt.py --build .planning/evolution/1.1/ 1.1
python3 evo_prompt.py --build .planning/evolution/1.1/ 1.1 --island 2
```
Output is the full markdown prompt text to stdout.

## Frontend Deliverables
- CLI `--build` outputs the complete evolution context as markdown to stdout
- Output is designed to be prepended to the existing task prompt by stop-hook.sh
- Markdown format renders clearly when read by Claude as part of its prompt

## Tests to Write (TDD-First)

### tests/python/test_evo_prompt.py
- test_build_prompt_with_population -- create fixture population with 5 approaches across multiple islands, verify output contains all 5 sections (Evolution Context, Parent Approach, What Went Wrong, Inspiration Approaches, Your Directive)
- test_build_prompt_empty_population -- empty db_path directory -> graceful minimal context with "No prior approaches" message, no crash
- test_parent_section_includes_metrics -- parent section shows score, generation number, island number
- test_inspiration_from_different_islands -- create population across 3 islands, verify inspirations are from a different island than the parent
- test_artifacts_truncated -- create approach with 2000-char error_trace, verify output clips to max_artifact_chars (500) with truncation marker
- test_directive_varies -- call _select_directive with 5 different generation numbers, verify at least 2 distinct directives returned
- test_format_approach -- format_approach returns markdown block containing score, generation, island, and prompt_addendum in a code block
- test_cli_build -- CLI --build with fixture population outputs text to stdout containing "## Evolution Context"
- test_build_prompt_single_island -- population with approaches only on island 0, verify build_prompt completes without error (inspirations may be empty list)

## Test Dependency Graph

| Test | File | Depends On | Guidance |
|------|------|-----------|----------|
| T1 | tests/python/test_evo_prompt.py | -- | Create evo_prompt.py. Import Approach and EvolutionDB from evo_db.py. Use tmp_path for fixture populations -- create a helper function that populates a temp evo_db with known approaches across islands. Reference /home/user/openevolve/openevolve/prompt/sampler.py for context construction patterns (build_prompt, _format_evolution_history, _identify_improvement_areas). |

Dispatch order:
- Wave 1: T1

## Key Links
- OpenEvolve reference: /home/user/openevolve/openevolve/prompt/sampler.py (prompt construction, evolution history formatting)
- Depends on: scripts/evo_db.py (Approach dataclass, EvolutionDB.sample, EvolutionDB.get_best)
- Consumer: hooks/stop-hook.sh (injects evolution context into next iteration prompt)
- Consumer: agents/executor.md (builds evolution context for parallel island agents)

## Technical Notes
- Dependencies: scripts/evo_db.py (Approach, EvolutionDB) + stdlib (json, os, random, argparse)
- Artifact truncation: slice to max_artifact_chars, append "... [truncated]" if clipped
- Directive selection uses `generation % len(directives)` as base index with random offset to vary
- The {score} and {percent} placeholders in directives are filled at format time from parent.metrics.test_pass_rate
- Empty population handling is critical -- first iteration has no prior approaches
- Single-island edge case: if all approaches are on one island, inspirations may be empty list
- The output markdown must be valid when prepended to an existing task prompt (no conflicting headers)
- Section headers use `##` (level 2) to nest under the task prompt's top-level structure
