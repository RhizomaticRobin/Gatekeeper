# Testing Overview

## Current State

**No automated tests exist.** The plugin has zero test files, no test framework configured, no CI pipeline.

Testing is currently:
- **Manual** — run commands and observe behavior
- **Implicit** — the VGL loop itself tests user projects via fetch-completion-token.sh
- **Specification-driven** — agent prompts define expected behavior

## What Exists

### fetch-completion-token.sh (verifier testing mechanism)
- Runs user project tests in independent subprocess
- Validates SHA-256 integrity of test command
- Checks for TODO/FIXME/stub patterns
- Issues 128-bit token only on full pass
- This tests the *user's code*, not gsd-vgl itself

### validate-plan.py (plan validation)
- Can be run standalone: `python3 scripts/validate-plan.py plan.yaml`
- Exit 0 = valid, Exit 1 = errors
- Checks structure, dependencies, required fields

### plan_utils.py CLI
- `--next-task`, `--complete-task`, `--unblocked-tasks`, `--all-ids`
- Can be tested via command line

## What Needs Testing

| Component | Priority | Framework | What to Test |
|-----------|----------|-----------|--------------|
| plan_utils.py | High | pytest | load, save, find_task, topological_sort, get_next_task |
| validate-plan.py | High | pytest | All validation rules, edge cases |
| stop-hook.sh | High | bats/bash | Token extraction, validation, auto-transition |
| guard-skills.sh | Medium | bats/bash | Blocking and pass-through |
| fetch-completion-token.sh | High | bats/bash | Token generation, integrity check, stub detection |
| transition-task.sh | Medium | bats/bash | Status update, next task finding |
| install.js | Low | jest/vitest | Copy, verify, MCP setup |
| intel-index.js | Low | jest/vitest | Graph DB operations |
| End-to-end pipeline | High | Custom | /quest → /cross-team → verifier → completion |

## Test Infrastructure Needed

```bash
# Python tests
pip install pytest
pytest tests/

# Bash tests (bats-core)
npm install -D bats
npx bats tests/

# Integration test
# Needs: Claude Code CLI, opencode MCP, sample project fixture
```
