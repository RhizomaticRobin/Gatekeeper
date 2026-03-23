# Architecture

## System Purpose
Gatekeeper is a Claude Code plugin that orchestrates software projects through spec-driven development with cryptographic verification. No task can be marked complete without passing independent verification by a Verifier agent in a fresh context.

## Core Pipeline (5 Stages)
```
Plan (/quest) -> Execute (/cross-team) -> Verify (Verifier agent) -> Transition (stop-hook) -> Autopilot (ralph.sh)
```

## The Gatekeeper Loop (GK)
The central abstraction. The executor cannot self-certify completion. Only the verifier can, and it operates in a fresh context with an infrastructure-generated prompt.

**Security chain:**
1. `setup-verifier-loop.sh` generates a 128-bit token, stores in `verifier-token.secret` (chmod 600)
2. `generate-verifier-prompt.sh` builds an immutable verifier prompt (executor cannot modify it)
3. Verifier runs tests via `fetch-completion-token.sh` (independent subprocess, SHA-256 integrity check on test command)
4. Token only revealed if tests pass AND no TODO/FIXME/stubs detected
5. `stop-hook.sh` extracts token from transcript, validates against secret file
6. On match: transition to next task. On mismatch: re-inject prompt, loop continues.

## Agent Hierarchy
```
User
 └─ /cross-team
     ├─ Team Mode (1+ tasks in parallel)
     │    ├─ Tester agents write tests (TDD Red)
     │    ├─ Assessor agents validate test quality
     │    ├─ Executor agents implement code (TDD Green)
     │    └─ Verifier agents validate (read-only) -> PASS/FAIL
     │
     └─ Multiple tasks -> Lead Orchestrator (no code)
          ├─ Spawns Executor sub-orchestrators (concurrent)
          ├─ Validates completion tokens
          ├─ Runs integration-checker at phase boundaries
          └─ Dispatches newly unblocked tasks
```

## State Management
- **Plan state:** `.claude/plan/plan.yaml` — YAML file with phases, tasks, statuses. Protected by flock for concurrent access.
- **Gatekeeper state:** `.claude/verifier-loop.local.md` — Markdown with YAML frontmatter (iteration, session_id, token ref, prompt). Created per Gatekeeper session.
- **Token state:** `.claude/verifier-token.secret` — Token + base64-encoded test command + SHA-256 hash. chmod 600.
- **Team state:** `.claude/gk-team-active` — Marker file for parallel execution mode. `.claude/gk-sessions/task-{id}/` per-task session dirs.
- **Project state:** `.planning/STATE.md`, `.planning/config.json` — Project-level tracking.
- **Evolution state:** `.planning/evolution/{task_id}/` — Per-task population database (approaches.jsonl + metadata.json).
- **History state:** `.planning/history/runs.jsonl` — Task execution outcomes.
- **Learnings state:** `.planning/learnings.jsonl` — Extracted learnings from verifier feedback.

## Data Flow Patterns
- **Plan -> Tasks:** plan.yaml contains task definitions; `prompt_file` references task-{id}.md files.
- **Task -> Agents:** Executor reads task prompt, writes tests, dispatches sub-agents with per-test guidance.
- **Agent -> Verifier:** After tests pass, executor spawns verifier via Task() with the generated prompt.
- **Verifier -> Hook:** Verifier outputs token in transcript; stop-hook extracts and validates it.
- **Hook -> Next Task:** On valid token, stop-hook calls transition-task.sh, sets up next Gatekeeper loop, blocks exit with new prompt.
- **Hook -> Evolution:** On failed iteration, stop-hook evaluates via evo_eval.py, stores in evo_db.py, builds evolution context via evo_prompt.py.

## Evolutionary Intelligence Layer
- **evo_db.py** — MAP-Elites population with island-based evolution. Approaches stored as JSONL. 3 islands, 2 feature dimensions (test_pass_rate, complexity), 10 bins per dimension.
- **evo_eval.py** — 3-stage cascade evaluator (collect-only -> partial -> full). Extracts test metrics, code metrics, artifacts.
- **evo_prompt.py** — Builds 5-section markdown prompts from population (context, parent, failures, inspirations, directive).
- **evo_pollinator.py** — Cross-task strategy migration based on file_scope similarity scoring.

## Hook Architecture (Claude Code Plugin Hooks)
- **Stop:** `stop-hook.sh` — Gatekeeper loop control. Validates tokens, auto-transitions tasks, injects evolution context.
- **PreToolUse (Skill):** `guard-skills.sh` — Blocks plan-modifying commands during active Gatekeeper loop.
- **PostToolUse (Skill):** `post-cross.sh` — Shows pipeline progress after /cross-team.
- **PostToolUse (Write|Edit):** `intel-index.js` — Indexes file exports/imports for codebase intelligence.
