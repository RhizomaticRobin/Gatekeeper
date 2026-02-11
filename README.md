# EvoGatekeeper (GSD-VGL)

A Claude Code plugin for spec-driven development with cryptographic verifier loops, TDD-first execution, and concurrent opencode agents.

## How It Works

EvoGatekeeper orchestrates software projects through a structured pipeline where no task can be marked complete without passing independent verification:

1. **Plan** (`/quest`) — Deep discovery + plan.yaml with phases, tasks, must_haves, TDD test specs, and per-task prompt files
2. **Execute** (`/cross-team`) — TDD-first implementation with parallel opencode agents, wave-based dispatch, and session continuations
3. **Verify** — Independent verifier in a fresh context checks tests, inspects code, and runs Playwright visual verification. A 128-bit cryptographic token is issued only on full pass
4. **Transition** — Stop hook validates the token, marks the task complete, and auto-transitions to the next task
5. **Autopilot** (`/autopilot`) — Ralph outer loop drives tasks to completion unattended with checkpoint commits

## Installation

Add the marketplace and install the plugin:

```bash
/plugin marketplace add RhizomaticRobin/gsd-vgl
/plugin install gsd-vgl@gsd-vgl
```

Or via the CLI outside of Claude Code:

```bash
claude plugin marketplace add RhizomaticRobin/gsd-vgl
claude plugin install gsd-vgl@gsd-vgl --scope user
```

The opencode MCP server ([Better-OpenCodeMCP](https://github.com/RhizomaticRobin/Better-OpenCodeMCP)) is bundled as a submodule and declared in `plugin.json`. It auto-builds on first launch — no manual setup needed.

## Architecture

```
User
 └─ /cross-team
     ├─ Single task → Executor (model: opus)
     │    ├─ Writes all tests (TDD Red)
     │    ├─ Dispatches gsd-builder opencode agents (1 per test, wave-based)
     │    │    ├─ Wave 1: fresh agents for independent tests (concurrent)
     │    │    └─ Wave 2+: session continuations for dependent tests
     │    ├─ Runs full test suite (TDD Green)
     │    └─ Spawns Verifier (model: opus, read-only)
     │         └─ PASS → token → stop hook → next task
     │
     └─ Multiple tasks → Lead Orchestrator (no code)
          ├─ Spawns Executor sub-orchestrators (concurrent, model: opus)
          │    └─ Each executor follows the same TDD workflow above
          ├─ Validates completion tokens against .secret files
          ├─ Runs integration-checker at phase boundaries
          └─ Dispatches newly unblocked tasks
```

All opencode agents use the **gsd-builder** agent profile — hardcoded server-side in the MCP server. No web access, no destructive operations, temperature 1.0, no step limit.

## Core Concepts

### Verifier-Gated Loop (VGL)

The executor cannot complete a task. Only the verifier can, and it operates in a fresh context with an immutable prompt. The verifier generates a 128-bit cryptographic token (`VGL_COMPLETE_[32-hex]`) only when all checks pass:

- Quantitative tests pass in an independent subprocess
- Code contains no stubs/TODOs/placeholders (grep check)
- Must_haves truths, artifacts, and key_links are satisfied
- Playwright visual verification passes (qualitative criteria)
- SHA-256 integrity check confirms the test command wasn't tampered with

The stop hook extracts the token from the transcript and validates it against `verifier-token.secret`. No match = loop continues.

### TDD-First with Wave Dispatch

Every task follows: write tests first, then implement, then verify.

Implementation uses a **Test Dependency Graph** from the task prompt:

```
| Test | File              | Depends On | Guidance                          |
|------|-------------------|------------|-----------------------------------|
| T1   | tests/auth.test   | -          | Create auth module, use bcrypt    |
| T2   | tests/api.test    | -          | Create API routes, mock DB        |
| T3   | tests/flow.test   | T1, T2     | Wire auth into API, test e2e      |
```

- **Wave 1**: T1 and T2 launch as fresh opencode agents (concurrent)
- **Wave 2**: T3 continues T2's session (most significant dependency) and is told to review T1's work
- Each agent gets exactly 1 test + specific implementation guidance
- `wait_for_completion()` after each wave; handle `input_required` questions via session continuation

### Goal-Backward Must-Haves

Verification checks three levels derived from the project goal:

- **Truths** — User-observable behaviors that must work ("User can log in and see dashboard")
- **Artifacts** — Files with real implementation, not stubs ("src/auth/route.ts exports POST handler")
- **Key Links** — Critical connections between components ("Login form POST /api/auth -> session cookie -> dashboard reads session")

### Integration Checkpoints

Phases in plan.yaml can set `integration_check: true`. When the last task in such a phase completes, an integration-checker agent is spawned before the next phase begins. It verifies cross-phase wiring: APIs consumed, data flows end-to-end, type contracts, no dead endpoints.

### Plan Format

```yaml
metadata:
  project: "Project Name"
  dev_server_command: "npm run dev"
  test_framework: "vitest"

phases:
  - id: 1
    name: "Authentication"
    goal: "Users can register and log in"
    integration_check: true
    must_haves:
      truths: ["User can log in with email/password"]
      artifacts: ["src/auth/route.ts with bcrypt"]
      key_links: ["Login form -> /api/auth -> session cookie"]
    tasks:
      - id: "1.1"
        name: "Auth API"
        status: pending
        depends_on: []
        prompt_file: "tasks/task-1.1.md"
        file_scope:
          owns: ["src/auth/", "tests/auth.test.ts"]
          reads: ["src/db/schema.ts"]
        wave: 1
        tests:
          quantitative:
            command: "npm test -- --run tests/auth.test.ts"
          qualitative:
            criteria: ["Login page accepts credentials and redirects to dashboard"]
        must_haves:
          truths: ["POST /api/auth returns session cookie on valid credentials"]
          artifacts: ["src/auth/route.ts"]
          key_links: ["route.ts -> bcrypt.compare -> session.create"]
```

## Commands

| Command | Description |
|---------|-------------|
| `/quest` | Plan a project — 6-phase discovery that generates plan.yaml + task prompt files |
| `/cross-team` | Execute tasks with TDD + VGL (single-task or parallel team orchestration) |
| `/bridge` | Standalone VGL for ad-hoc tasks outside a plan |
| `/autopilot` | Launch Ralph outer loop in a new terminal for unattended execution |
| `/new-project` | Initialize a project with deep requirements gathering |
| `/research` | Domain research before planning (parallel researcher agents) |
| `/map-codebase` | Analyze existing codebase (7-dimension brownfield analysis) |
| `/progress` | Project status dashboard with metrics |
| `/verify-milestone` | Integration verification across phases |
| `/debug` | Systematic debugging with persistent state (scientific method) |
| `/settings` | Configure model profiles and preferences |
| `/run-away` | Cancel the active VGL loop |
| `/help` | Command reference |

## Agents

All agents run on model: opus with restricted tool access.

| Agent | Role | Disallowed Tools |
|-------|------|------------------|
| `planner` | Creates plan.yaml + task-{id}.md with must_haves, wave assignments, TDD specs | Edit, WebSearch, Task |
| `executor` | TDD-first execution: writes tests, dispatches opencode agents, runs suite, spawns verifier | WebFetch, WebSearch |
| `verifier` | Independent verification with cryptographic token — tests, code inspection, Playwright | Write, Edit, WebFetch, WebSearch, Task |
| `plan-checker` | Pre-execution plan quality gate (6 verification dimensions) | Write, Edit, WebFetch, WebSearch, Task |
| `integration-checker` | Cross-phase wiring verification at phase boundaries | Write, Edit, WebFetch, WebSearch, Task |
| `project-researcher` | Domain research — tech stacks, patterns, pitfalls | Write, Edit, Task |
| `phase-researcher` | Phase-specific technical deep dives — APIs, libraries, integration points | Write, Edit, Task |
| `codebase-mapper` | Brownfield codebase analysis (7 dimensions) | Write, Edit, WebFetch, WebSearch, Task |
| `debugger` | Scientific method debugging with persistent `.planning/debug/` state | WebFetch, WebSearch, Task |

### gsd-builder (opencode agent)

The opencode MCP server hardcodes all spawned agents to use the `gsd-builder` profile defined in `templates/opencode.json`:

- No web access (websearch/webfetch disabled)
- Bash (ask permission), Edit/Write (allowed)
- Temperature 1.0, no step limit
- 10-minute timeout per `wait_for_completion()` call

## Hooks

| Hook | Event | Purpose |
|------|-------|---------|
| `stop-hook.sh` | Stop | Prevents exit during VGL. Validates token, auto-transitions to next task, injects integration check instructions at phase boundaries |
| `guard-skills.sh` | PreToolUse/Skill | Blocks plan-modifying commands during active VGL |
| `post-cross.sh` | PostToolUse/Skill | Shows next task in pipeline after /cross-team |
| `intel-index.js` | PostToolUse/Write,Edit | Indexes file exports/imports for codebase intelligence (bundled with sql.js) |

## Project Structure

```
gsd-vgl/
├── .claude-plugin/
│   ├── plugin.json                  Plugin manifest + MCP server declaration
│   └── marketplace.json             Self-contained marketplace definition
├── .gitmodules                      Submodule reference
├── package.json                     npm package config (v1.0.0)
├── Better-OpenCodeMCP/              Submodule — opencode MCP server
│   └── dist/index.js                Built MCP entry point
├── agents/                          9 agent definitions (.md with frontmatter)
├── bin/
│   ├── install.js                   Legacy installer (npx fallback)
│   ├── opencode-mcp.sh              MCP server launcher (auto-builds on first run)
│   ├── ralph.sh                     Autopilot outer loop
│   └── lib/                         Shell libraries (state, budget, display, ...)
├── commands/                        14 slash commands
├── hooks/
│   ├── hooks.json                   Hook event registration
│   ├── stop-hook.sh                 VGL loop control + auto-transition
│   ├── guard-skills.sh              Skill blocker during VGL
│   ├── post-cross.sh                Post-execution info
│   └── intel-index.js               Codebase intelligence indexer
├── scripts/
│   ├── setup-verifier-loop.sh       Initialize VGL state + token
│   ├── generate-verifier-prompt.sh  Build immutable verifier prompt
│   ├── fetch-completion-token.sh    Independent test execution for token
│   ├── transition-task.sh           Mark complete + find next task
│   ├── cross-team-setup.sh          Plan validation + task dispatch setup
│   ├── validate-plan.py             Plan.yaml structural validation
│   ├── plan_utils.py                Shared plan utilities (load, save, find, sort)
│   ├── next-task.py                 Find next unblocked task
│   ├── get-unblocked-tasks.py       Find all unblocked tasks
│   ├── check-file-conflicts.py      Detect file scope overlaps
│   ├── parse-args.py                Argument parser for /bridge
│   ├── build-hooks.js               esbuild bundler for hook scripts
│   └── team-orchestrator-prompt.md  Lead orchestrator template
├── templates/
│   ├── opencode.json                gsd-builder agent config
│   ├── project.md                   .planning/project.md template
│   ├── requirements.md              .planning/requirements.md template
│   ├── roadmap.md                   .planning/roadmap.md template
│   ├── state.md                     .planning/state.md template
│   ├── config.json                  Default project configuration
│   ├── task-prompt.md               task-{id}.md template
│   ├── plan-summary.md              Plan summary template
│   └── codebase/                    7-dimension codebase analysis templates
├── references/
│   ├── tdd-opencode-workflow.md     TDD + concurrent execution reference
│   ├── verification-patterns.md     Artifact verification strategies
│   ├── model-profiles.md            Model selection & routing
│   └── git-integration.md           Git commit strategy
└── workflows/
    ├── discovery-phase.md           Discovery phase workflow
    ├── execute-phase.md             Execution phase workflow
    └── verify-phase.md              Verification phase workflow
```

## Verification Immutability

The verifier cannot be tricked or bypassed:

1. **128-bit token** in `verifier-token.secret` (chmod 600) — executor never sees it
2. **SHA-256 integrity** — test command is base64-encoded with hash; tampering is detected
3. **Guard hook** — blocks plan-modifying commands during active VGL
4. **Fresh context** — verifier spawned via `Task()` with infrastructure-generated prompt
5. **Independent execution** — `fetch-completion-token.sh` runs tests in a fresh subprocess
6. **Stub detection** — grep for TODO/FIXME/placeholder patterns in implementation files

## Ralph Autopilot

The `ralph.sh` outer loop drives unattended multi-task execution:

```bash
/autopilot          # Launch in a new terminal
./bin/ralph.sh      # Or run directly
```

Ralph spawns fresh Claude Code instances per task, creates checkpoint commits (`checkpoint(task-{id}): {summary}`), handles failures with retry/skip/abort, and tracks budget usage.

## License

MIT
