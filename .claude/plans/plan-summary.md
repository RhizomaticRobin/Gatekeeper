# Plan: EvoGatekeeper Evolution Engine

## Overview
Replace the static heuristic scripts (wave_sizer, task_router, failure_classifier, budget_scheduler, auto_fixer, dep_resolver, progress_advisor) with a genuine OpenEvolve-style evolutionary intelligence engine. The "program" being evolved is the approach/strategy addendum given to builder agents. Each VGL iteration becomes a generation — evaluate the attempt with multi-dimensional metrics, store in a MAP-Elites population, sample parent + inspirations from islands, and build rich evolution context for the next iteration.

## Tech Stack
- Language: Python (scripts) + Bash (hooks) — stdlib + PyYAML only
- Testing: pytest (Python), bats (Bash)
- Algorithms: MAP-Elites, island-based populations, cascade evaluation, cross-task pollination
- Reference: /home/user/openevolve/openevolve/ (database.py, evaluator.py, prompt/sampler.py)

## must_haves (Project-Level)
### Truths
- VGL iterations use evolutionary selection instead of simple retry
- Population of approaches grows across iterations with MAP-Elites quality-diversity
- Parallel islands explore different strategies simultaneously
- Successful approaches migrate between similar tasks via cross-pollination
- No static heuristic scripts remain

### Artifacts
- scripts/evo_db.py, evo_eval.py, evo_prompt.py, evo_pollinator.py
- Modified hooks/stop-hook.sh and agents/executor.md
- tests/python/test_evo_*.py and tests/bash/evo-*.bats

## Task Graph

| ID | Task | Wave | Depends On | Key must_haves | Status |
|----|------|------|------------|----------------|--------|
| 1.1 | Population DB (MAP-Elites + islands) | 1 | — | Approach model, 3-tier sampling, island isolation, JSONL persistence | pending |
| 1.2 | Cascade evaluator | 1 | — | 3-stage pipeline, multi-dim metrics, artifact capture | pending |
| 1.3 | Prompt evolution builder | 2 | 1.1 | Parent+inspirations context, directive variation, empty pop graceful | pending |
| 2.1 | Stop-hook evolution integration | 3 | 1.1,1.2,1.3 | Evaluate→store→sample→inject cycle, graceful degradation | pending |
| 2.2 | Executor parallel islands | 3 | 1.1,1.3 | 2-3 candidates per iteration, best selected for verifier | pending |
| 2.3 | Cross-task pollination | 3 | 1.1 | Similarity scoring, inspiration island, threshold filtering | pending |
| 3.1 | Remove static heuristics | 4 | 2.1,2.2,2.3 | 7 scripts + 7 test files deleted, all references updated | pending |
| 3.2 | E2E evolution smoke test | 5 | 3.1 | Fixture project, population growth, cascade eval, pollination | pending |

## Architecture Decisions
- **No separate LLM API call for mutation**: The executor agent IS Claude — it naturally "mutates" when given evolution context (parent approach, failure artifacts, inspirations)
- **JSONL + JSON persistence**: Matches existing project patterns (run_history.py, learnings.py). Approaches in JSONL, feature maps in JSON metadata
- **3 islands by default**: Balances diversity vs cost. Island 0-1 for evolution, island 2 reserved for cross-pollination imports
- **Feature dimensions: test_pass_rate x complexity**: Quality vs diversity tradeoff. Configurable per project
- **Cascade evaluation**: Stage 1 (collect-only, 2s) → Stage 2 (3 tests) → Stage 3 (full suite). Cheap elimination of bad approaches
- **run_history.py kept**: Still used for audit trail in transition-task.sh. Not redundant with evolution DB (different purpose)

## Dev Server
Command: `echo ok`
URL: http://localhost:3000
