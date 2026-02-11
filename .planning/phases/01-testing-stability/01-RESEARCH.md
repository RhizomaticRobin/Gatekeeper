# Phase 1 Research: Testing & Stability

> Research completed on 2026-02-11. 5 topics investigated by parallel research agents.

## Executive Summary

Phase 1 establishes a test infrastructure across three languages (Python, Bash, Node.js) and hardens the VGL loop against concurrency issues. The research confirms that **pytest**, **bats-core**, and **vitest** are the right tools for their respective domains, and identifies specific patterns needed for each.

The most impactful finding is the **file locking vulnerability** in plan.yaml writes. The current `save_plan()` function performs a direct `open(path, "w")` with no locking, and `transition-task.sh` does a read-modify-write cycle without concurrency protection. The recommended fix is a two-layer approach: `flock`-based serialization (interoperable between Bash and Python via `fcntl.flock`) plus atomic writes via tmp + `os.replace()`.

For hook testing, the critical contract detail is that **JSON output is only processed on exit 0** — exit 2 ignores stdout entirely and feeds stderr to Claude as an error. This means test assertions must check exit codes first, then conditionally parse JSON output.

## Topic Summaries

### 1. pytest for Python Testing
- **Recommendation:** Use pytest with `tmp_path`, `capsys`, and `monkeypatch` fixtures
- **Confidence:** HIGH
- **Key Insight:** plan_utils.py functions split cleanly into pure functions (take dict, return data) and I/O functions (read/write YAML). Test pure functions directly, use `tmp_path` for I/O functions. Import `validate-plan.py` (hyphenated) via `importlib.util.spec_from_file_location`.
- **Details:** See `pytest-python-research.md`

### 2. bats-core for Bash Testing
- **Recommendation:** Install via npm (`npm install -D bats bats-support bats-assert bats-file`), use PATH-based mocking for external commands
- **Confidence:** HIGH
- **Key Insight:** bats runs each `@test` in a subprocess, so `set -e` in scripts interacts with test assertions. Use `run` to capture exit code + output without aborting. For hooks that read stdin, pipe JSON directly: `echo "$JSON" | run bash "$HOOK"`.
- **Details:** See `bats-bash-research.md`

### 3. vitest for Node.js Testing
- **Recommendation:** Use vitest with `vi.mock()` for fs/child_process, `vi.spyOn(process, 'exit')` for exit handling
- **Confidence:** HIGH
- **Key Insight:** install.js has extensive top-level side effects (arg parsing, banner, main dispatch) that execute on import. Tests must use `vi.resetModules()` + dynamic `await import()` for each scenario. Long-term, extract pure functions to a separate module.
- **Details:** See `vitest-nodejs-research.md`

### 4. File Locking in Bash/Python
- **Recommendation:** Use `flock` (Bash) / `fcntl.flock` (Python) on a `plan.yaml.lock` sidecar file, plus atomic writes via tmp + `os.replace()`
- **Confidence:** HIGH
- **Key Insight:** Bash `flock` and Python `fcntl.flock` use the same `flock(2)` syscall and interoperate on the same lock file. This means transition-task.sh (Bash) and plan_utils.py (Python) can safely share a lock. The lock must span the entire read-modify-write cycle, not just the write.
- **Details:** See `file-locking-research.md`

### 5. Claude Code Hook Testing
- **Recommendation:** Plain bash test harness with jq assertions (or bats with helpers). Pipe fixture JSON into hooks, assert on exit code + stdout JSON.
- **Confidence:** MEDIUM (Claude Code hook contract not formally documented — inferred from code)
- **Key Insight:** Exit code is the primary control signal. Exit 0 = JSON parsed from stdout. Exit 2 = stdout ignored, stderr shown as error. Any other exit = silent failure. stop-hook.sh is the most complex (~280 lines) and depends on transcript files, state files, and external scripts — needs extensive fixture setup.
- **Details:** See `hook-testing-research.md`

## Architecture Implications

### Test Directory Structure
```
tests/
├── conftest.py              pytest shared fixtures
├── python/                  pytest tests
│   ├── test_plan_utils.py
│   └── test_validate_plan.py
├── bash/                    bats tests
│   ├── test_helper/
│   │   └── common-setup.bash
│   ├── fixtures/            Shared test data (YAML, JSON)
│   ├── guard-skills.bats
│   ├── stop-hook.bats
│   ├── fetch-completion-token.bats
│   └── transition-task.bats
└── node/                    vitest tests
    ├── install.test.js
    └── intel-index.test.js
```

### Dependencies to Add
```json
// package.json devDependencies
{
  "vitest": "^3.x",
  "bats": "^1.x",
  "bats-support": "github:bats-core/bats-support",
  "bats-assert": "github:bats-core/bats-assert",
  "bats-file": "github:bats-core/bats-file"
}
```
```
# Python (pip or requirements-dev.txt)
pytest
pyyaml
```

### File Locking Changes
- `plan_utils.py`: Add `fcntl.flock` context manager around save_plan and update_task_status
- `transition-task.sh`: Wrap read-modify-write in `flock 9; ... 9>/path/to/plan.yaml.lock`
- Both use same lock file: `.claude/plan/plan.yaml.lock`

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Hook contract changes in Claude Code update | Medium | High | Pin Claude Code version in CI, test against known version |
| bats-core subprocess model masks script errors | Medium | Medium | Always check `$status` explicitly, use `assert_failure` |
| vitest CJS-to-ESM transform breaks import behavior | Low | Medium | Use dynamic imports with `vi.resetModules()` |
| flock not available on all platforms (macOS) | Low | Low | flock is standard on Linux; macOS has it via coreutils |
| Test fixtures diverge from actual Claude Code JSON format | Medium | Medium | Extract sample JSON from real sessions, version fixtures |

## Open Questions

- What exact JSON fields does Claude Code pass to Stop hooks? (inferred from code, not formally documented)
- Does Claude Code support hook timeouts? (if a hook hangs, does it kill it?)
- Can bats tests run in parallel safely with shared fixture files?
- Should we use `memfs` for vitest fs mocking or stick with `vi.mock('fs')`?

## Cross-References

- **Requirements:** R-001 (pytest), R-002 (bats), R-003 (bats + hook harness), R-004 (vitest), R-005 (flock)
- **Dependencies discovered:** pytest, bats-core, bats-support, bats-assert, bats-file, vitest
- **Codebase concerns addressed:** CONCERNS.md #1 (no tests), #2 (race conditions)
