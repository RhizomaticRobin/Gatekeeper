# Architecture Overview

## Pattern: Verifier-Gated Loop (VGL)

No task can be marked complete without independent cryptographic verification. The executor cannot self-complete — only the verifier can issue a 128-bit token, and only when all checks pass.

## Execution Flow

```
/cross-team
  ↓
cross-team-setup.sh → validate plan, find unblocked tasks
  ↓
┌─────────── Single Task ───────────┐  ┌────── Multi-Task (Team) ──────┐
│ Executor (model: opus)            │  │ Lead Orchestrator (no code)   │
│  1. Read task-{id}.md             │  │  ├─ Executor A (Task subagent)│
│  2. Write ALL tests (TDD Red)     │  │  ├─ Executor B (Task subagent)│
│  3. Parse Test Dependency Graph   │  │  └─ Executor C (Task subagent)│
│  4. Wave 1: fresh opencode agents │  │  Each executor runs full VGL  │
│  5. Wave 2+: session continuations│  │  Lead validates tokens, marks │
│  6. Run full test suite (Green)   │  │  complete, dispatches next    │
│  7. Spawn Verifier                │  │  Integration checks at phase  │
└───────────────────────────────────┘  │  boundaries                   │
  ↓                                    └───────────────────────────────┘
Verifier (fresh context, read-only, model: opus)
  1. Load immutable verifier-prompt.local.md
  2. Run tests via fetch-completion-token.sh
  3. Check must_haves (truths, artifacts, key_links)
  4. Playwright visual verification
  5. PASS → VGL_COMPLETE_{32-hex} token
  ↓
Stop Hook
  1. Extract token from transcript
  2. Validate against verifier-token.secret
  3. Match → transition-task.sh → next task (loop)
  4. No match → re-inject prompt → executor retries
```

## Component Hierarchy

```
Commands (user entry points)
  → Agents (orchestration roles)
    → Scripts (utilities)
      → Hooks (event handlers)
        → State files (.claude/ directory)
```

## State Files

| File | Purpose | Written By | Read By |
|------|---------|-----------|---------|
| `.claude/plan/plan.yaml` | Master task list | planner, transition-task.sh | all |
| `.claude/plan/task-{id}.md` | Task specification | planner | executor, verifier |
| `.claude/verifier-loop.local.md` | VGL state (iteration, session) | setup-verifier-loop.sh | stop-hook.sh |
| `.claude/verifier-token.secret` | 128-bit token + SHA-256 hash | setup-verifier-loop.sh | fetch-completion-token.sh |
| `.claude/verifier-prompt.local.md` | Immutable verifier prompt | generate-verifier-prompt.sh | verifier agent |
| `.claude/vgl-team-active` | Team mode flag | team orchestrator | guard-skills.sh |

## Key Design Decisions

1. **Executor/Verifier separation** — Verifier runs in fresh context, can't be influenced
2. **Cryptographic token + SHA-256** — Prevents forgery and test command tampering
3. **Wave-based dispatch** — Independent tests parallel, dependent tests continue sessions
4. **Stop hook as loop controller** — Returns `decision: "block"` to keep session alive
5. **Guard skills hook** — Blocks conflicting commands during active VGL
