# Concerns & Tech Debt

## Critical

### No automated tests
All 90+ source files are untested. Regressions can't be detected before release. Core logic (plan_utils.py, stop-hook.sh, fetch-completion-token.sh) is complex and error-prone without tests.

### No error recovery
If VGL loop crashes mid-execution, state files remain in `.claude/` and require manual cleanup. No rollback or resume capability.

## High Priority

### Race conditions in team mode
Multiple concurrent executors can call transition-task.sh simultaneously, risking plan.yaml corruption. No file locking or atomic writes.

### Incomplete plan validation
validate-plan.py misses: file scope conflicts, must_haves format validation, prompt_file existence check, test command syntax validation.

### Weak token validation
Token extracted via grep from transcript — no check that it appears in verifier output specifically. No replay protection, no expiration.

### Hardcoded agent model
gsd-builder uses `zai-coding-plan/glm-4.7` (in opencode.json). Not configurable per-project. If model becomes unavailable, system breaks.

## Medium Priority

### Insufficient input validation
Scripts assume well-formed input. Task IDs not validated against pattern. Iteration counts not bounds-checked. Potential for unexpected behavior on malformed data.

### Limited logging
Only stop-hook.sh has DEBUG_LOG. Other scripts have minimal error output. Hard to debug failures in production.

### Submodule version not pinned
Better-OpenCodeMCP submodule points to main branch. Breaking changes upstream could break the plugin.

## Low Priority

### Static template files
Templates don't reflect plugin version. Users may have stale configs after upgrade.

### Inconsistent error messages
Different scripts use different error formats (`PLAN_NOT_FOUND:` vs `Error:` vs plain text).

### No performance monitoring
Can't measure task duration, agent utilization, or identify bottlenecks.

## TODOs Found

| Area | Description |
|------|-------------|
| Integration prefix | INTEGRATION_PREFIX constructed in stop-hook.sh — recently wired but not battle-tested |
| Ralph autopilot | Shell libraries in bin/lib/ — large codebase not fully audited |
| Intel index | sql.js graph DB in hooks — feature completeness unknown |
