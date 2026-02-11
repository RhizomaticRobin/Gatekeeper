# Task 3.1: Remove Static Heuristics and Update References

## Goal (from must_haves)
**Truths:**
- All 7 static heuristic scripts are deleted: wave_sizer.py, task_router.py, failure_classifier.py, budget_scheduler.py, auto_fixer.py, dep_resolver.py, progress_advisor.py
- All 7 corresponding test files are deleted
- No remaining references to deleted scripts in hooks/, agents/, commands/, or scripts/
- README.md contains "evolutionary" or "evolution" in place of old "Adaptive Intelligence" section
- All 4 evo scripts exist: evo_db.py, evo_eval.py, evo_prompt.py, evo_pollinator.py

**Artifacts:**
- (7 scripts deleted)
- (7 test files deleted)
- hooks/stop-hook.sh (references cleaned)
- agents/executor.md (references cleaned)
- commands/cross-team.md (references cleaned)
- commands/quest.md (references cleaned)
- scripts/team-orchestrator-prompt.md (references cleaned)
- README.md (updated)
- commands/help.md (updated)
- tests/bash/evo-migration.bats

## Context
Tasks 1.1-1.3 created the evolutionary intelligence scripts (evo_db.py, evo_eval.py, evo_prompt.py). Task 2.1 integrated the evolution engine into the stop-hook. Task 2.2 added evolution to the executor. Task 2.3 added the pollinator. This task removes the old static heuristic scripts that the evolution engine replaces and cleans up all references to them.

The old scripts were hand-coded heuristics that attempted to predict task behavior (wave_sizer.py), classify failures (failure_classifier.py), route tasks (task_router.py), allocate budgets (budget_scheduler.py), auto-fix errors (auto_fixer.py), resolve dependencies (dep_resolver.py), and advise on progress (progress_advisor.py). The evolutionary approach replaces ALL of these with a single population-based system that learns strategies from actual execution outcomes.

## Backend Deliverables

### Files to Delete
Scripts:
- `scripts/wave_sizer.py`
- `scripts/task_router.py`
- `scripts/failure_classifier.py`
- `scripts/budget_scheduler.py`
- `scripts/auto_fixer.py`
- `scripts/dep_resolver.py`
- `scripts/progress_advisor.py`

Tests:
- `tests/python/test_wave_sizer.py`
- `tests/python/test_task_router.py`
- `tests/python/test_failure_classifier.py`
- `tests/python/test_budget_scheduler.py`
- `tests/python/test_auto_fixer.py`
- `tests/python/test_dep_resolver.py`
- `tests/python/test_progress_advisor.py`

### References to Update

**hooks/stop-hook.sh:**
- Remove any remaining `learnings.py` calls that were not already replaced by task 2.1
- Remove any references to `wave_sizer.py`, `task_router.py`, `failure_classifier.py`, `budget_scheduler.py`
- Ensure EVOLUTION_PREFIX is the only intelligence injection (from task 2.1)

**agents/executor.md:**
- Should already reference evolution engine (from task 2.2)
- Remove any references to old scripts if present

**commands/cross-team.md:**
- Remove references to `wave_sizer`, `task_router`, `budget_scheduler`
- Update any mentions of "adaptive" dispatch to "evolution-guided" dispatch

**commands/quest.md:**
- Update phase 3 and phase 4 descriptions that reference old heuristic scripts
- Replace with descriptions of the evolution engine

**scripts/team-orchestrator-prompt.md:**
- Remove references to old scripts
- Update to reference evo_db.py, evo_eval.py, evo_prompt.py where appropriate

**README.md:**
- Replace "Adaptive Intelligence" section with "Evolutionary Intelligence" section
- Replace "Self-Healing" section content with evolution-based description
- Mention MAP-Elites, islands, cascade evaluation, cross-task pollination
- Keep the section concise (10-15 lines)

**commands/help.md:**
- Update feature list to replace old heuristic features with evolutionary intelligence features

## Frontend Deliverables
- Running `ls scripts/wave_sizer.py` returns "No such file" (all old scripts gone)
- Running `grep -r "wave_sizer\|task_router\|failure_classifier\|budget_scheduler\|auto_fixer\|dep_resolver\|progress_advisor" scripts/ hooks/ agents/ commands/` returns no matches
- README.md mentions "evolution" or "evolutionary"

## Tests to Write (TDD-First)

### tests/bash/evo-migration.bats
- test_no_deleted_scripts_exist -- verify all 7 scripts (wave_sizer.py, task_router.py, failure_classifier.py, budget_scheduler.py, auto_fixer.py, dep_resolver.py, progress_advisor.py) do not exist in scripts/
- test_no_deleted_tests_exist -- verify all 7 test files do not exist in tests/python/
- test_no_references_in_scripts -- grep for old script names in scripts/ directory returns no matches (exit code 1)
- test_no_references_in_hooks -- grep for old script names in hooks/ directory returns no matches
- test_no_references_in_agents -- grep for old script names in agents/ directory returns no matches
- test_readme_has_evolution -- README.md contains "evolution" or "evolutionary" (case-insensitive)
- test_evo_scripts_exist -- all 4 evo scripts present: evo_db.py, evo_eval.py, evo_prompt.py, evo_pollinator.py in scripts/

## Test Dependency Graph

| Test | File | Depends On | Guidance |
|------|------|-----------|----------|
| T1 | tests/bash/evo-migration.bats | -- | Delete the 7 listed scripts and 7 test files using rm. Update all reference files (hooks/stop-hook.sh, agents/executor.md, commands/cross-team.md, commands/quest.md, scripts/team-orchestrator-prompt.md, README.md, commands/help.md). Write bats tests that verify: (1) deleted files do not exist via [ ! -f ... ], (2) grep for old names in scripts/, hooks/, agents/, commands/ returns exit code 1, (3) README.md contains "evolution", (4) evo scripts exist via [ -f ... ]. Use PLUGIN_ROOT from common-setup.bash for paths. |

Dispatch order:
- Wave 1: T1

## Key Links
- Replaced by: scripts/evo_db.py (task 1.1), scripts/evo_eval.py (task 1.2), scripts/evo_prompt.py (task 1.3), scripts/evo_pollinator.py (task 2.3)
- Integration: hooks/stop-hook.sh (task 2.1), agents/executor.md (task 2.2)
- Old heuristic scripts: scripts/wave_sizer.py, task_router.py, failure_classifier.py, budget_scheduler.py, auto_fixer.py, dep_resolver.py, progress_advisor.py

## Technical Notes
- Delete files FIRST, then update references, then run tests -- tests verify the final state
- Use `git rm` if in a git repo, otherwise plain `rm`
- Some of the old scripts may not exist yet if they were never implemented (they are in the old plan but may be pending) -- `rm -f` handles this gracefully
- The grep tests should use `grep -rq` (quiet mode) and check exit codes, not output
- Be careful not to delete `scripts/learnings.py` in this task -- it is still used as a reference and may be removed separately later
- Some reference files (commands/cross-team.md, commands/quest.md) may not exist -- update only if they exist
- The README.md update should be a surgical replacement of the "Adaptive Intelligence" section, not a full rewrite
