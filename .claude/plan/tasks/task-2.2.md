# Task 2.2: Executor Parallel Island Support

## Goal (from must_haves)
**Truths:**
- Executor Step 2.5 checks for existing population at .planning/evolution/{task_id}/
- When population has >= 3 approaches, executor samples from different islands and spawns parallel opencode agents
- Each parallel agent receives the task prompt + a different approach's prompt_addendum
- All candidate results are evaluated via evo_eval.py and stored back in the population
- The BEST candidate's work is used for subsequent TDD verification
- When population is empty or < 3, normal TDD flow proceeds without evolution context

**Artifacts:**
- agents/executor.md (modified)
- references/tdd-opencode-workflow.md (modified, if exists)
- tests/python/test_evo_executor.py

## Context
The executor agent (agents/executor.md) orchestrates task implementation using TDD-first methodology with opencode MCP concurrency. Currently, it reads a task spec, writes tests, dispatches opencode agents per the Test Dependency Graph, and spawns a Verifier.

This task adds an evolution-guided approach selection step BEFORE the TDD dispatch. When a population exists from prior iterations (built by the stop-hook in task 2.1), the executor can spawn multiple parallel agents -- each trying a different evolved approach from different islands. The best candidate's work then feeds into the standard TDD verification flow.

This is the parallel exploration mechanism: instead of trying one approach per VGL iteration, the executor can explore 2-3 approaches concurrently. Combined with the stop-hook storing results, this accelerates evolution convergence.

## Backend Deliverables

### Modify `agents/executor.md`:

Add new step between Step 2 and Step 3:

```markdown
## Step 2.5: Evolution-Guided Approach Selection

If a population exists at `.planning/evolution/{task_id}/`:

1. **Check population stats:**
   ```bash
   python3 scripts/evo_db.py --db-path .planning/evolution/{task_id}/ --stats
   ```

2. **If population has >= 3 approaches, run parallel island exploration:**
   - Sample approaches from different islands:
     ```bash
     python3 scripts/evo_db.py --db-path .planning/evolution/{task_id}/ --sample 0
     python3 scripts/evo_db.py --db-path .planning/evolution/{task_id}/ --sample 1
     python3 scripts/evo_db.py --db-path .planning/evolution/{task_id}/ --sample 2
     ```
   - For each sampled approach, spawn an opencode agent:
     ```
     launch_opencode(task="""
     APPROACH STRATEGY:
     {approach.prompt_addendum}

     YOUR TASK:
     {original_task_prompt}

     Implement the task following the approach strategy above.
     Run the test command when done: {test_command}
     """)
     ```
   - Wait for all candidates to complete via wait_for_completion()
   - Evaluate each candidate's work:
     ```bash
     python3 scripts/evo_eval.py --evaluate "{test_command}"
     ```
   - Store ALL results back in the population:
     ```bash
     python3 scripts/evo_db.py --db-path .planning/evolution/{task_id}/ --add '{metrics_json}'
     ```
   - Use the BEST candidate's work (highest test_pass_rate) for subsequent TDD steps
   - If all candidates fail, proceed with normal TDD flow

3. **If population is empty or < 3 approaches:** Skip evolution, proceed directly to Step 3 (normal TDD flow).
```

### Update TDD dispatch (Step 3) to include evolution context:

When dispatching opencode agents for TDD, if an evolution population exists, include the best approach's prompt_addendum in each agent's prompt:

```markdown
### Evolution Context in TDD Agents

If Step 2.5 selected a winning approach, include it in every TDD agent prompt:

```
launch_opencode(task="""
APPROACH STRATEGY (from evolution):
{best_approach.prompt_addendum}

Make the following test pass: {test_file}

GUIDANCE:
{guidance from test dependency graph}

RULES:
- Only modify files listed in the guidance
- Do not modify the test file itself
- Follow the approach strategy above for implementation decisions
- Run the test after implementation to confirm it passes
""")
```
```

### Update `references/tdd-opencode-workflow.md` (if exists):
Add a section on evolution-guided dispatch describing the Step 2.5 flow.

## Frontend Deliverables
- Executor logs to stderr: "Evolution: found N approaches across K islands"
- Executor logs: "Evolution: spawning 3 island candidates"
- Executor logs: "Evolution: candidate island-0 scored 0.75, island-1 scored 0.90, island-2 scored 0.60"
- Executor logs: "Evolution: using island-1 approach (best score 0.90)"
- When population is empty: "Evolution: no population found, proceeding with normal TDD"

## Tests to Write (TDD-First)

### tests/python/test_evo_executor.py
Test the evo_db.py CLI patterns that executor.md describes:
- test_stats_returns_population_info -- create fixture population with 5 approaches, run evo_db.py --stats, verify JSON output has total_approaches and per_island fields
- test_sample_from_multiple_islands -- create fixture population across 3 islands, run evo_db.py --sample 0, --sample 1, --sample 2, verify each returns a different parent approach
- test_approach_addendum_format -- verify prompt_addendum field in sampled approach is a non-empty string suitable for injection into a task prompt
- test_store_candidate_results -- create fixture, run evo_db.py --add with metrics JSON, verify approach count increases
- test_best_candidate_selection -- create fixture with approaches of varying test_pass_rate, run evo_db.py --best, verify returned approach has the highest score
- test_empty_population_skips_evolution -- run evo_db.py --stats on empty directory, verify total_approaches is 0 (triggers skip logic in executor)

## Test Dependency Graph

| Test | File | Depends On | Guidance |
|------|------|-----------|----------|
| T1 | tests/python/test_evo_executor.py | -- | Update agents/executor.md to add Step 2.5 and evolution context in TDD dispatch. Write integration tests that verify evo_db.py CLI works correctly for the patterns described in executor.md. Create fixture populations in tmp_path using evo_db.py --add, then test --stats, --sample, --best. Import subprocess to call evo_db.py as CLI. Alternatively, import EvolutionDB and Approach directly and test the Python API. |

Dispatch order:
- Wave 1: T1

## Key Links
- Integration target: agents/executor.md (Step 2.5 addition)
- Depends on: scripts/evo_db.py (task 1.1), scripts/evo_eval.py (task 1.2)
- Related: hooks/stop-hook.sh (task 2.1, builds population that executor reads)
- Executor current flow: agents/executor.md Steps 1-6

## Technical Notes
- The executor is a Claude agent prompt (agents/executor.md), not executable code -- changes are to the markdown instructions
- Tests verify the CLI tools the executor will call, not the executor prompt itself
- Parallel island exploration is optional: it only activates when population >= 3 approaches
- The "best candidate's work" means the executor uses that agent's session for subsequent TDD steps
- If all parallel candidates score 0.0, fall back to normal TDD without evolution context
- Island count is fixed at 3 (matching evo_db.py defaults), so at most 3 parallel candidates
- The --sample CLI returns a parent + inspirations; the executor uses parent.prompt_addendum as the approach
- Evolution context in TDD agents is additive -- it does not replace the existing GUIDANCE/RULES structure
