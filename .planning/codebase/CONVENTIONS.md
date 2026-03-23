# Conventions

## Naming Patterns
- **Shell scripts:** kebab-case (`setup-verifier-loop.sh`, `cross-team-setup.sh`)
- **Python modules:** snake_case (`plan_utils.py`, `evo_db.py`, `run_history.py`)
- **Python functions:** snake_case (`load_plan`, `get_next_task`, `_plan_lock`)
- **Python classes:** PascalCase (`EvolutionDB`, `CascadeEvaluator`, `Approach`)
- **JavaScript files:** kebab-case (`install-lib.js`, `intel-index.js`, `build-hooks.js`)
- **Agent definitions:** kebab-case (`executor.md`, `plan-checker.md`, `codebase-mapper.md`)
- **Commands:** kebab-case (`cross-team.md`, `map-codebase.md`, `quest.md`)
- **Templates:** kebab-case or snake_case (`task-prompt.md`, `config.json`)
- **Environment variables:** UPPER_SNAKE_CASE (`PLUGIN_ROOT`, `GATEKEEPER_PLAN_LOCKED`, `CLAUDE_PLUGIN_ROOT`)
- **Gatekeeper tokens:** `GK_COMPLETE_` prefix + 32 hex chars

## File Organization
- Agent .md files have YAML frontmatter with: name, description, model, tools, disallowedTools, color
- Command .md files have YAML frontmatter with: description, argument-hint, allowed-tools
- Both use XML-style section tags: `<role>`, `<execution_flow>`, `<critical_rules>`, `<output_format>`
- Shell scripts start with `#!/bin/bash`, `set -euo pipefail`, then plugin root resolution
- Python scripts start with docstring, sys.path manipulation for scripts/ imports, then class/function definitions

## Error Message Format (Standardized in Phase 5)
All scripts follow: `Error:` line + `Try:` recovery line
```bash
echo "Error: Plan file not found at $PLAN_FILE" >&2
echo "Try: Run /gatekeeper:quest to generate a plan." >&2
```

## Import Patterns
- Python: `sys.path.insert(0, os.path.dirname(...))` then `from plan_utils import load_plan`
- Shell: `PLUGIN_ROOT="$(dirname "$(dirname "$(realpath "$0")")")"` then source or call scripts
- Commands: `${CLAUDE_PLUGIN_ROOT}` variable for plugin root paths in bash blocks

## State File Patterns
- Frontmatter parsing: `awk 'NR==1 && /^---$/{next} /^---$/{exit} NR>1{print}'`
- Field extraction: `grep '^field:' | sed 's/field: *//'`
- File locking: `fcntl.flock()` in Python, `flock -x 9` in Bash, with `GATEKEEPER_PLAN_LOCKED` env var to prevent deadlock
- Atomic writes: `tempfile.mkstemp()` + `os.replace()` in Python

## Code Style
- Shell: Double quotes around variables, `[[ ]]` for conditionals, `|| true` for grep under pipefail
- Python: Type hints on class attributes and function signatures, dataclasses for structured data
- Markdown prompts: Structured with headers, code blocks, critical rules sections, numbered steps
- Debug logging: `debug()` function writing to `/tmp/gatekeeper-stop-hook.debug.log`
- stderr for user-visible status messages, stdout for machine-parseable output (JSON, status codes)

## CLI Patterns
- Python scripts are both importable libraries and CLI tools (`if __name__ == "__main__": main()`)
- CLI uses argparse with mutually exclusive groups
- Output is JSON to stdout, messages to stderr
- Exit codes: 0 = success, 1 = error, 2 = special (e.g., "all tasks complete" in transition-task.sh)

## Status Codes in Shell Output
- `CROSS_TEAM_FAILED` / `CROSS_TEAM_OK` — cross-team-setup.sh routing
- `TASK_COMPLETE:{id}:{token}` / `TASK_FAILED:{id}:{reason}` — executor output protocol
