# GSD-VGL: Get Shit Done - Verifier Gated Loop

A Claude Code plugin combining spec-driven development with cryptographic verifier loops, TDD-first execution, and opencode MCP concurrency.

## What It Does

GSD-VGL orchestrates complex software projects through a structured pipeline:

1. **Plan** (`/quest`) - Generate a plan.yaml with phases, tasks, must_haves, and per-task prompt files
2. **Execute** (`/cross-team`) - TDD-first task execution with independent verification
3. **Verify** - Cryptographic token-gated verification ensures tests pass independently
4. **Autopilot** (`/autopilot`) - Ralph outer loop drives tasks to completion unattended

## Core Concepts

### Verifier-Gated Loop (VGL)
Each task runs in a loop: executor implements → verifier checks → pass/fail. The verifier operates in a fresh context with an immutable prompt, generating a 128-bit cryptographic token only when all tests pass independently.

### TDD-First Workflow
Every task follows: write tests → implement → verify. Tests are written before any implementation code. For tasks with multiple independent test files, opencode MCP agents run concurrently (one per test file).

### Goal-Backward Must-Haves
Verification checks three levels:
- **Truths** - User-observable behaviors that must work
- **Artifacts** - Files with real implementation (not stubs)
- **Key Links** - Critical connections between components

### Plan Format
```yaml
phases:
  - id: 1
    name: "Phase Name"
    must_haves:
      truths: [...]
      artifacts: [...]
      key_links: [...]
    tasks:
      - id: "1.1"
        name: "Task Name"
        status: pending
        depends_on: []
        prompt_file: "tasks/task-1.1.md"
        file_scope: { owns: [], touches: [] }
        wave: 1
```

## Installation

```bash
# Clone into your Claude Code plugins directory
git clone <repo-url> ~/.claude/plugins/gsd-vgl

# Or install via npm
npm install -g gsd-vgl
```

## Commands

| Command | Description |
|---------|-------------|
| `/quest` | Plan a project - generates plan.yaml + task prompt files |
| `/cross` | **[DEPRECATED]** Use `/cross-team` instead |
| `/cross-team` | Execute tasks with TDD + VGL (single or parallel) |
| `/bridge` | Standalone VGL for ad-hoc tasks |
| `/run-away` | Cancel the active VGL loop |
| `/new-project` | Initialize a new project with deep requirements gathering |
| `/research` | Domain research before planning |
| `/map-codebase` | Analyze existing codebase structure |
| `/autopilot` | Launch ralph.sh outer loop in a new terminal |
| `/progress` | Show project status dashboard |
| `/settings` | Configure model profiles and preferences |
| `/verify-milestone` | Integration verification across phases |
| `/debug` | Systematic debugging with persistent state |
| `/help` | Command reference |

## Agents

| Agent | Role |
|-------|------|
| `planner` | Creates plan.yaml + task-{id}.md files |
| `executor` | TDD-first task execution + opencode concurrency |
| `verifier` | Independent verification with cryptographic token |
| `plan-checker` | Pre-execution plan quality gate |
| `integration-checker` | Cross-phase wiring verification |
| `project-researcher` | Domain research |
| `phase-researcher` | Phase-specific technical deep dives |
| `codebase-mapper` | Codebase analysis |
| `debugger` | Scientific method debugging |

## Task Execution Lifecycle

```
/cross-team → validate plan → find unblocked tasks → setup VGL
    │
    ▼
Executor Agent:
  1. Read task-{id}.md
  2. Write ALL tests first (TDD Red phase)
  3. launch_opencode() × N for concurrent implementation
  4. wait_for_completion() → integrate
  5. Run full test suite (Green phase)
  6. Spawn verifier
    │
    ▼
Verifier Agent (fresh context, immutable prompt):
  1. Inspect source against must_haves
  2. Run tests independently (fetch-completion-token.sh)
  3. Playwright visual verification
  4. PASS: {token} or FAIL: {reasons}
    │
    ▼
Stop Hook:
  Token match → transition to next task → continue
  No token → re-inject prompt → executor fixes
```

## Ralph Autopilot

The `ralph.sh` outer loop drives unattended execution:

```bash
# Launch in a new terminal
/autopilot

# Or run directly
./bin/ralph.sh
```

Ralph iterates through tasks, creates checkpoint commits (`checkpoint(task-{id}): {summary}`), handles failures with retry/skip/abort options, and tracks budget usage.

## Project Structure

```
gsd-vgl/
├── .claude-plugin/plugin.json    Plugin manifest
├── package.json                  Node package config
├── commands/                     14 slash commands
├── agents/                       9 agent definitions
├── hooks/                        Hook scripts + hooks.json
├── scripts/                      Infrastructure scripts
├── bin/                          ralph.sh + shell libraries
├── templates/                    Project/plan/state templates
├── references/                   Model profiles, TDD workflow
└── workflows/                    Execution, verification workflows
```

## Verification Immutability

The verifier prompt cannot be modified by the executor agent:
1. 128-bit cryptographic token in `verifier-token.secret` (chmod 600)
2. SHA-256 test command integrity check
3. Guard skills hook blocks plan modification during VGL
4. Fresh verifier context via Task() with infrastructure-generated prompt
5. Independent test execution in isolated subprocess

## License

MIT
