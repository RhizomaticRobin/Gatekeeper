# v1 Requirements — EvoGatekeeper

## Stability & Testing

### R-001: Test coverage for plan utilities
- **Description:** Unit tests for plan_utils.py (load, save, find_task, get_next_task, get_all_unblocked_tasks, topological_sort)
- **Acceptance Criteria:**
  - [ ] Tests cover all public functions
  - [ ] Edge cases: empty plan, circular deps, missing fields
  - [ ] Tests run via `pytest` or `python -m unittest`

### R-002: Test coverage for shell scripts
- **Description:** Integration tests for setup-verifier-loop.sh, transition-task.sh, fetch-completion-token.sh, cross-team-setup.sh
- **Acceptance Criteria:**
  - [ ] Each script has a test that runs it with fixture data
  - [ ] Token generation and validation paths tested
  - [ ] Error paths tested (missing files, bad YAML, invalid tokens)

### R-003: Test coverage for hooks
- **Description:** Tests for stop-hook.sh, guard-skills.sh, post-cross.sh
- **Acceptance Criteria:**
  - [ ] Stop hook token extraction and validation tested
  - [ ] Guard skills blocking and pass-through tested
  - [ ] Integration prefix injection tested

### R-004: Test coverage for installer
- **Description:** Tests for bin/install.js (copy, verify, MCP setup)
- **Acceptance Criteria:**
  - [ ] Copy function tested with mock filesystem
  - [ ] Verification function tested with missing files
  - [ ] MCP launcher script tested (auto-build detection)

### R-005: Harden VGL loop edge cases
- **Description:** Fix edge cases in the verifier-gated loop: stale state files, concurrent writes, token race conditions
- **Acceptance Criteria:**
  - [ ] Stale verifier-loop.local.md detected and cleaned
  - [ ] Concurrent task transitions don't corrupt plan.yaml
  - [ ] Token file permissions enforced (chmod 600)

## Self-Improving System

### R-006: Run history database
- **Description:** Persistent storage of task execution outcomes — what was attempted, what passed/failed, how many iterations, time taken, agent session IDs
- **Acceptance Criteria:**
  - [ ] SQLite or JSON-based store in `.planning/history/`
  - [ ] Each task completion records: task_id, iterations, pass/fail, duration, failure_reasons
  - [ ] History survives across sessions

### R-007: Learnings accumulator
- **Description:** After each task completes (or fails), extract actionable learnings and store them for future use
- **Acceptance Criteria:**
  - [ ] Learnings extracted from verifier feedback (failure reasons, what fixed it)
  - [ ] Stored in `.planning/learnings.md` or structured format
  - [ ] Learnings injected into future task prompts for similar tasks

### R-008: Pattern recognition across runs
- **Description:** Detect recurring failure patterns (e.g., "tests in auth/ always fail on first try due to missing env") and proactively warn or adjust
- **Acceptance Criteria:**
  - [ ] Common failure patterns catalogued after 3+ occurrences
  - [ ] Warnings injected into executor prompts when pattern matches
  - [ ] Patterns are project-scoped (not global)

### R-009: Strategy adaptation
- **Description:** System adjusts execution strategy based on historical performance — e.g., tasks that always need 3+ iterations get more detailed prompts
- **Acceptance Criteria:**
  - [ ] Task prompts enriched with historical context when available
  - [ ] Retry budget adjusted per-task based on history
  - [ ] Executor told "this type of task typically needs X" when pattern exists

## Smarter Orchestration

### R-010: Dynamic wave sizing
- **Description:** Instead of fixed wave dispatch, size waves based on available resources, task complexity estimates, and historical performance
- **Acceptance Criteria:**
  - [ ] Wave size considers number of files in scope (larger scope = smaller wave)
  - [ ] Historical task duration informs concurrent dispatch limits
  - [ ] Configurable max concurrent agents

### R-011: Adaptive retry with diagnosis
- **Description:** When a task fails verification, diagnose the failure type and choose the right retry strategy (re-run, modify prompt, escalate to human)
- **Acceptance Criteria:**
  - [ ] Failure classified as: test_failure, build_error, timeout, scope_creep, flaky_test
  - [ ] Each failure type has a different retry strategy
  - [ ] After 2 retries with same failure, escalate with diagnosis

### R-012: Agent routing by task characteristics
- **Description:** Route tasks to agent configurations optimized for their type — e.g., API tasks get different guidance than UI tasks
- **Acceptance Criteria:**
  - [ ] Task type detected from deliverables and file scope (api, ui, data, infra)
  - [ ] Agent guidance templates per task type
  - [ ] Planner tags tasks with detected type

### R-013: Resource-aware scheduling
- **Description:** Track API usage/budget and adjust dispatch accordingly — don't spawn 10 agents when budget is low
- **Acceptance Criteria:**
  - [ ] Budget tracking integrated with Ralph's existing budget.sh
  - [ ] Wave size reduced when remaining budget < 30%
  - [ ] Warning emitted when budget critically low

## End-to-End Autonomy

### R-014: Auto-fix integration failures
- **Description:** When integration-checker reports NEEDS_FIXES, automatically spawn a fix agent instead of requiring human intervention
- **Acceptance Criteria:**
  - [ ] CRITICAL integration issues auto-fixed via targeted agent
  - [ ] Fix verified by re-running integration-checker
  - [ ] If auto-fix fails twice, escalate to human

### R-015: Autonomous dependency resolution
- **Description:** When a task fails due to missing dependencies or setup issues, detect and resolve automatically
- **Acceptance Criteria:**
  - [ ] Missing npm packages detected and installed
  - [ ] Missing environment variables detected and prompted once
  - [ ] Missing test fixtures created from task context

### R-016: Progress-aware decision making
- **Description:** System makes smart decisions based on overall project progress — e.g., skip non-critical tasks when behind schedule, prioritize blockers
- **Acceptance Criteria:**
  - [ ] Critical path tasks prioritized over non-blocking work
  - [ ] When >70% complete, focus on remaining blockers
  - [ ] Progress metrics available to orchestrator for decisions

### R-017: End-to-end smoke test
- **Description:** A single integration test that runs /quest on a small sample project and verifies the full pipeline works through to verification
- **Acceptance Criteria:**
  - [ ] Sample project defined in `tests/fixtures/`
  - [ ] Test runs /quest → /cross-team → verifier → completion
  - [ ] Test verifies plan.yaml state transitions correct
  - [ ] Test runs in CI-compatible mode (no interactive prompts)

## UX & Polish

### R-018: Rename to EvoGatekeeper
- **Description:** Rename the project from gsd-vgl to EvoGatekeeper across all files, marketplace, and npm package
- **Acceptance Criteria:**
  - [ ] Package name updated in package.json
  - [ ] Plugin name updated in plugin.json and marketplace.json
  - [ ] All command prefixes remain `/gsd-vgl:` (backward compat) or migrate to new prefix
  - [ ] README and help updated

### R-019: Improved error messages
- **Description:** All script failures produce actionable error messages with recovery instructions
- **Acceptance Criteria:**
  - [ ] Every `exit 1` path has a descriptive error message
  - [ ] Error messages include "what to try next"
  - [ ] No raw stack traces shown to users

### R-020: First-run onboarding
- **Description:** When plugin loads for the first time, show a brief welcome with key commands
- **Acceptance Criteria:**
  - [ ] Detects first run (no `.planning/` directory)
  - [ ] Shows 3-line welcome with `/gsd-vgl:help` pointer
  - [ ] Non-intrusive (doesn't block workflow)

## Out of Scope
- Multi-user authentication or team features
- GUI/web dashboard — CLI-only
- Non-Claude AI provider support
- Monetization, licensing, or commercial features
- Plugin marketplace ecosystem management (focus on this plugin only)
- Cross-machine state sync (learnings are project-local)
