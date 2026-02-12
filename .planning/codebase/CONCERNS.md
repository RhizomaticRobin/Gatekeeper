# Concerns

## Technical Debt

### Mixed Language Complexity
The codebase uses Bash, Python, and JavaScript for different components. Cross-language calls (Bash calling Python, Python called from Bash with env vars) create fragile interfaces. The `sys.path.insert(0, ...)` pattern in every Python script is a code smell — a proper Python package structure would be cleaner.

### No Python Package Structure
Python scripts in `scripts/` are flat files that import each other via sys.path manipulation. There is no `setup.py`, `pyproject.toml`, or `__init__.py` for the scripts directory. This makes testing harder and IDE support weaker.

### Frontmatter Parsing is Fragile
YAML frontmatter in `.claude/verifier-loop.local.md` is parsed with awk/sed/grep chains in Bash. This was hardened in Phase 1 (sed -> awk for embedded `---` markers) but remains brittle compared to a proper parser.

### Large Shell Scripts
`stop-hook.sh` (~400 lines) and `ralph.sh` (~550 lines) plus its lib/ (~2,500 lines total) are substantial Bash programs. Complex control flow in Bash is harder to test and maintain than equivalent Python/JS.

## Known Issues

### Evolution DB Cold Start
On first iteration of a task, the evolution population is empty. The pollinator (`evo_pollinator.py`) migrates approaches from similar completed tasks, but if no tasks are completed yet, the first task gets no evolutionary guidance.

### GSD_VGL_PLAN_LOCKED Deadlock Prevention
The `GSD_VGL_PLAN_LOCKED=1` environment variable is used to prevent deadlock when a parent Bash process holds the plan.yaml flock and calls a Python child. If this env var is not properly propagated (e.g., in a subprocess without `export`), deadlock can occur.

### Team Mode Stop Hook Skip
When `.claude/vgl-team-active` exists, the stop hook skips all VGL processing. If a team execution is interrupted without cleanup, this marker file can persist and break subsequent single-task VGL executions. Manual removal of `.claude/vgl-team-active` is the recovery.

## Performance Concerns

### Cascade Evaluator Subprocess Overhead
`evo_eval.py` runs up to 3 subprocess invocations (collect-only, partial, full) per evaluation. Each is a fresh process spawn. For test suites with fast individual tests, the overhead of spawning is significant relative to test execution time.

### JSONL Scan for History/Learnings
`run_history.py` and `learnings.py` read the entire JSONL file on every query. For long-running projects with many tasks, this linear scan becomes slow. A SQLite backend (like intel-index.js uses) would scale better.

## Security Considerations

### Token in Transcript
The VGL completion token appears in the Claude Code transcript. The stop-hook greps for it. An adversarial executor agent could hypothetically try to forge a token, but:
- The token has 128-bit entropy (32 hex chars)
- The executor never sees the token value
- The verifier can only obtain it via `fetch-completion-token.sh` which runs tests independently
- SHA-256 integrity check prevents test command tampering

### eval in fetch-completion-token.sh
Line 93: `TEST_OUTPUT=$(eval "$TEST_COMMAND" 2>&1)` uses eval on a string from the token file. This is protected by the SHA-256 integrity check (the test command is base64-encoded at setup time and verified before execution), but `eval` with untrusted input is inherently risky.

### chmod 600 on Token File
`verifier-token.secret` is chmod 600, but this only protects against other system users. The Claude Code process running as the same user can still read it. The real protection is that the executor agent's prompt tells it not to read the file, and the verifier agent has Write/Edit disabled.

## Warnings from Phase Integration Checks
- Phase 3 and Phase 4 integration checks both noted 2 warnings (non-critical). These were accepted and not addressed, representing minor gaps in cross-phase documentation or optional features.
