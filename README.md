# Gatekeeper

A Claude Code plugin for spec-driven development with cryptographic verifier loops, TDD-first execution, and concurrent opencode agents.

## How It Works

Gatekeeper orchestrates software projects through a structured pipeline where no task can be marked complete without passing independent verification:

1. **Plan** (`/quest`) -- Deep discovery + plan.yaml with phases, tasks, must_haves, TDD test specs, and per-task prompt files
2. **Test** -- Tester agent researches the domain (WebSearch + Context7), writes comprehensive tests, passes `assess_tests` quality gate
3. **Execute** (`/cross-team`) -- TDD-first implementation with parallel opencode agents, wave-based dispatch, and session continuations
4. **Verify** -- Independent verifier in a fresh context checks tests, inspects code, and runs Playwright visual verification. A 128-bit cryptographic token is issued only on full pass
5. **Transition** -- Stop hook validates the token, marks the task complete, and auto-transitions to the next task
6. **Iterate** -- Failed verifications loop back through execution with evolutionary intelligence informing retry strategies

## Prerequisites

| Dependency | Minimum Version | Purpose |
|------------|----------------|---------|
| **Node.js** | >= 18.0.0 | MCP servers, hook scripts, installer |
| **npm** | (bundled with Node) | Package management |
| **Python 3** | >= 3.8 | Plan utilities, evolution engine, validation |
| **git** | any recent | Cloning, submodules |
| **jq** | any recent | JSON parsing in hook scripts |
| **Claude Code** | latest | The CLI tool that runs the plugin |
| **OpenCode** | latest | Agent dispatch for gsd-builder agents |
| **ANTHROPIC_API_KEY** | -- | Auto-detected from subscription or set manually (see below) |

### Authentication for Verification Agents

The `verify_task` and `assess_tests` MCP tools spawn independent Claude Code subprocesses via the Agent SDK. Authentication is resolved automatically in this order:

1. **`ANTHROPIC_API_KEY` env var** -- if set, used directly
2. **OAuth token from `~/.claude/.credentials.json`** -- if you're logged in to Claude Code with a subscription (Pro/Max), the OAuth access token is read and used automatically

Most users don't need to do anything -- just be logged in to Claude Code. If auto-detection fails:

```bash
export ANTHROPIC_API_KEY=sk-ant-...  # https://console.anthropic.com/settings/keys
```

### Check prerequisites

```bash
node --version    # >= 18.0.0
python3 --version # >= 3.8
git --version
jq --version
claude --version  # Claude Code CLI
opencode version  # OpenCode CLI
echo $ANTHROPIC_API_KEY  # Optional if logged in via subscription
```

## Installation

### Quick Install (automated)

```bash
git clone --recurse-submodules https://github.com/RhizomaticRobin/gatekeeper.git
cd gatekeeper
bash scripts/bootstrap.sh
```

The bootstrap script checks prerequisites, builds both MCP servers, installs the plugin to Claude Code, and verifies the installation.

### Manual Install (step by step)

#### 1. Install Claude Code

If Claude Code is not installed:

```bash
# Via npm (recommended)
npm install -g @anthropic-ai/claude-code

# Verify
claude --version
```

See [Claude Code docs](https://docs.anthropic.com/en/docs/claude-code) for alternative installation methods.

#### 2. Install OpenCode

If OpenCode is not installed:

```bash
# Via the official installer
curl -fsSL https://opencode.ai/install | bash

# Verify
opencode version
```

OpenCode installs to `~/.opencode/bin/`. Make sure it's on your PATH.

#### 3. Clone the repository

```bash
git clone --recurse-submodules https://github.com/RhizomaticRobin/gatekeeper.git
cd gatekeeper
```

If you already cloned without `--recurse-submodules`:

```bash
git submodule update --init --recursive
```

#### 4. Build the OpenCode MCP server

```bash
cd Better-OpenCodeMCP
npm install --production=false
npm run build
cd ..
```

Verify: `ls Better-OpenCodeMCP/dist/index.js` should exist.

#### 5. Build the Verifier MCP server

```bash
cd verifier-mcp
npm install --production=false
npm run build
cd ..
```

Verify: `ls verifier-mcp/dist/index.js` should exist.

#### 6. Build hook scripts

```bash
npm install
npm run build:hooks
```

Verify: `ls hooks/dist/intel-index.js` should exist.

#### 7. Install the plugin into Claude Code

**Option A: Via the plugin system (recommended)**

```bash
# From inside Claude Code
/plugin marketplace add /path/to/gatekeeper
/plugin install gatekeeper
```

Or via the CLI:

```bash
claude plugin marketplace add /path/to/gatekeeper
claude plugin install gatekeeper --scope user
```

Use `--scope project` for a single project, or `--scope local` for project-local (gitignored).

**Option B: Via the legacy npx installer**

```bash
# From the gatekeeper directory
node bin/install.js --global
```

This copies the plugin to `~/.claude/plugins/gatekeeper/`, builds MCP servers, and makes scripts executable.

**Option C: Via npm (from any directory)**

```bash
npx gatekeeper --global
```

#### 8. Verify the installation

Restart Claude Code (or start a new session), then:

```bash
# Check MCP servers are loaded
/mcp
```

You should see:
- `plugin:gatekeeper:opencode-mcp` -- tools: `launch_opencode`, `wait_for_completion`, `opencode_sessions`
- `plugin:gatekeeper:verifier-mcp` -- tools: `verify_task`, `assess_tests`

```bash
# Check commands are available
/gatekeeper:help
```

### Updating

After pulling new changes:

```bash
cd gatekeeper
git pull --recurse-submodules

# Rebuild MCP servers if source changed
cd Better-OpenCodeMCP && npm install && npm run build && cd ..
cd verifier-mcp && npm install && npm run build && cd ..

# Rebuild hooks if changed
npm run build:hooks

# Update the installed plugin
claude plugin update gatekeeper
```

Then restart Claude Code for MCP servers to reload.

### Uninstalling

```bash
claude plugin uninstall gatekeeper
claude plugin marketplace remove gatekeeper
```

### Other plugin commands

```bash
# Disable without uninstalling
claude plugin disable gatekeeper

# Re-enable
claude plugin enable gatekeeper
```

## Architecture

```
User
 └─ /cross-team -> Lead Orchestrator (never writes code)
      ├─ Phase 1: Spawn Tester agents (per task, concurrent)
      │    └─ Each Tester (model: sonnet, HAS web access):
      │         ├─ Researches domain via WebSearch + Context7
      │         ├─ Writes comprehensive tests (TDD Red)
      │         └─ Calls assess_tests(task_id) quality gate
      │              └─ Test assessor agent (opus, read-only)
      │                   └─ PASS -> TESTS_READY
      │
      ├─ Phase 2: Spawn Executor agents (per task with ready tests)
      │    └─ Each Executor (model: sonnet, no web access):
      │         ├─ Reads pre-written test files
      │         ├─ Dispatches gsd-builder opencode agents (1 per test, wave-based)
      │         │    ├─ Wave 1: fresh agents for independent tests (concurrent)
      │         │    └─ Wave 2+: session continuations for dependent tests
      │         ├─ Runs full test suite (TDD Green)
      │         └─ Calls verify_task(task_id) via verifier-mcp
      │              └─ Verifier agent (opus, Playwright + tests)
      │                   └─ PASS -> token -> orchestrator validates -> next task
      │
      ├─ Validates completion tokens against .secret files
      ├─ Runs integration-checker at phase boundaries
      └─ Dispatches newly unblocked tasks
```

## Core Concepts

### Verifier-Gated Loop (VGL)

The executor cannot complete a task. Only the verifier can, and it operates in a fresh context with an immutable prompt. The verifier generates a 128-bit cryptographic token (`VGL_COMPLETE_[32-hex]`) only when all checks pass:

- Quantitative tests pass in an independent subprocess
- Code contains no stubs/TODOs/placeholders (grep check)
- Must_haves truths, artifacts, and key_links are satisfied
- Playwright visual verification passes (qualitative criteria)
- SHA-256 integrity check confirms the test command wasn't tampered with

The stop hook extracts the token from the transcript and validates it against `verifier-token.secret`. No match = loop continues.

### Test Quality Gate (assess_tests)

Before implementation begins, the tester agent's tests must pass an independent assessment:

- Are tests internally consistent (no contradictions)?
- Do they cover happy paths, error paths, edge cases, and boundaries?
- Is every must_have represented by test assertions?
- Are assertions meaningful (not trivial `expect(true)`)?
- Is test data realistic (not "foo", "bar")?

The assessor returns PASS/FAIL with specific issues. Tests are iteratively fixed until they pass.

### TDD-First with Wave Dispatch

Every task follows: write tests first (tester), then implement (executor), then verify.

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

- **Truths** -- User-observable behaviors that must work ("User can log in and see dashboard")
- **Artifacts** -- Files with real implementation, not stubs ("src/auth/route.ts exports POST handler")
- **Key Links** -- Critical connections between components ("Login form POST /api/auth -> session cookie -> dashboard reads session")

### Security Model

Agent access is restricted through multiple layers:

- **Scope guards** (`guard-scope.sh`) -- PreToolUse hook blocks Read/Bash/Grep/Glob access to infrastructure files (tokens, prompts, plugin source, agent definitions) during VGL execution
- **Plan lock** (`guard-plan.sh`) -- PreToolUse hook blocks Write/Edit to plan.yaml and task files once execution starts. Unlocked on completion or `/run-away`
- **Orchestrator guard** (`guard-orchestrator.sh`) -- Blocks Write/Edit/WebFetch/WebSearch for the lead orchestrator during team mode
- **Token-at-call-time** -- Cryptographic tokens are generated inside the MCP tool handler at invocation, not at setup. Agents cannot pre-read secret files
- **Token validation** -- `plan_utils.py --complete-task` requires a valid token to mark tasks done
- **Prompt opacity** -- Verifier/assessor prompts are loaded by MCP tools internally; calling agents never see them

### Integration Checkpoints

Phases in plan.yaml can set `integration_check: true`. When the last task in such a phase completes, an integration-checker agent is spawned before the next phase begins. It verifies cross-phase wiring: APIs consumed, data flows end-to-end, type contracts, no dead endpoints.

### Evolutionary Intelligence

Gatekeeper uses an evolutionary approach to improve execution strategies across iterations and tasks:

- **MAP-Elites Population Database** (`evo_db.py`) -- Stores diverse approaches in a multi-dimensional grid indexed by island and behavioral descriptors
- **Island-Based Parallel Exploration** -- On retry iterations with sufficient population (>= 3 approaches), the executor samples strategies from different islands and spawns parallel agents
- **Cascade Evaluation** (`evo_eval.py`) -- Each attempt is evaluated on multiple dimensions (test pass rate, duration, complexity)
- **Evolutionary Prompt Construction** (`evo_prompt.py`) -- Builds context-aware prompts from the population, surfacing best strategies and common failure patterns
- **Cross-Task Pollination** (`evo_pollinator.py`) -- Successful strategies from similar completed tasks are migrated into new task populations

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
| `/quest` | Plan a project -- 6-phase discovery that generates plan.yaml + task prompt files |
| `/cross-team` | Execute tasks with TDD + VGL (single-task or parallel team orchestration) |
| `/bridge` | Standalone VGL for ad-hoc tasks outside a plan |
| `/research` | Domain research before planning (parallel researcher agents) |
| `/map-codebase` | Analyze existing codebase (7-dimension brownfield analysis) |
| `/progress` | Project status dashboard with metrics |
| `/verify-milestone` | Integration verification across phases |
| `/debug` | Systematic debugging with persistent state (scientific method) |
| `/settings` | Configure model profiles and preferences |
| `/run-away` | Cancel the active VGL loop |
| `/help` | Command reference |

## Agents

| Agent | Role | Model | Key Tools |
|-------|------|-------|-----------|
| `tester` | Writes comprehensive tests, calls `assess_tests` quality gate | sonnet | WebSearch, WebFetch, Context7 |
| `executor` | TDD-first execution: dispatches opencode agents, runs suite, calls `verify_task` | sonnet | opencode MCP, Context7 |
| `verifier` | Independent verification with cryptographic token -- tests, code inspection, Playwright | opus | Playwright, Bash (read-only) |
| `planner` | Creates plan.yaml + task-{id}.md with must_haves, wave assignments, TDD specs | sonnet | Read, Write, Bash |
| `plan-checker` | Pre-execution plan quality gate (6 verification dimensions) | sonnet | Read, Bash, Grep, Glob |
| `integration-checker` | Cross-phase wiring verification at phase boundaries | sonnet | Read, Bash, Grep, Glob |
| `project-researcher` | Domain research -- tech stacks, patterns, pitfalls | sonnet | WebSearch, WebFetch |
| `phase-researcher` | Phase-specific technical deep dives -- APIs, libraries, integration points | sonnet | WebSearch, WebFetch |
| `codebase-mapper` | Brownfield codebase analysis (7 dimensions) | sonnet | Read, Bash, Grep, Glob |
| `debugger` | Scientific method debugging with persistent state | sonnet | Read, Write, Edit, Bash |

### gsd-builder (opencode agent)

The opencode MCP server spawns agents using the `gsd-builder` profile defined in `templates/opencode.json`:

- No web access (websearch/webfetch disabled)
- **Context7 MCP server** for library documentation research
- Research-first prompt -- agents must look up APIs via Context7 before implementing
- Bash (ask permission), Edit/Write (allowed)
- Temperature 1.0, no step limit

#### How Context7 MCP gets to opencode agents

```
templates/opencode.json          Canonical config (checked into gatekeeper repo)
       |
       v (copied at setup time by cross-team-setup.sh / setup-verifier-loop.sh)
<project>/opencode.json          Deployed to project root
       |
       v (opencode reads from cwd on spawn)
opencode run --agent gsd-builder  Spawned by Better-OpenCodeMCP
       |
       v (opencode loads "mcp" section from opencode.json)
Context7 MCP server started       npx -y @upstash/context7-mcp
       |
       v (tools available to agent)
resolve-library-id, query-docs    Agent can research any library docs
```

## Hooks

| Hook | Event | Purpose |
|------|-------|---------|
| `stop-hook.sh` | Stop | Prevents exit during VGL. Validates token, auto-transitions to next task |
| `guard-scope.sh` | PreToolUse: Read, Bash, Grep, Glob | Blocks agent access to infrastructure files during VGL |
| `guard-plan.sh` | PreToolUse: Write, Edit | Locks plan.yaml and task files during execution |
| `guard-orchestrator.sh` | PreToolUse: Write, Edit, WebFetch, WebSearch | Blocks code-writing by the lead orchestrator in team mode |
| `guard-skills.sh` | PreToolUse: Skill | Blocks plan-modifying commands during active VGL |
| `post-cross.sh` | PostToolUse: Skill | Shows next task in pipeline after /cross-team |
| `intel-index.js` | PostToolUse: Write, Edit | Indexes file exports/imports for codebase intelligence |

## MCP Servers

### opencode-mcp (`plugin:gatekeeper:opencode-mcp`)

Agent dispatch via the OpenCode CLI. Source: `Better-OpenCodeMCP/`.

| Tool | Purpose |
|------|---------|
| `launch_opencode(task="...")` | Spawn a fresh gsd-builder agent |
| `launch_opencode(sessionId="...", task="...")` | Continue an existing agent's session |
| `launch_opencode(tasks=[...])` | Batch-launch multiple agents |
| `wait_for_completion(taskIds=[...])` | Block until agents finish |
| `opencode_sessions(status="active")` | Check running agents |

### verifier-mcp (`plugin:gatekeeper:verifier-mcp`)

Verification and test assessment. Source: `verifier-mcp/`.

| Tool | Purpose |
|------|---------|
| `verify_task(task_id)` | Spawn independent verifier agent, returns PASS/FAIL with token |
| `assess_tests(task_id)` | Spawn independent test assessor, returns PASS/FAIL with issues |

Both MCP servers auto-install dependencies and auto-build on first launch via their launcher scripts in `bin/`.

## Project Structure

```
gatekeeper/
├── .claude-plugin/
│   ├── plugin.json                  Plugin manifest + MCP server declarations
│   └── marketplace.json             Self-contained marketplace definition
├── .gitmodules                      Submodule reference
├── package.json                     npm package config (v1.0.0)
├── Better-OpenCodeMCP/              Submodule -- opencode MCP server
│   └── dist/index.js                Built MCP entry point
├── verifier-mcp/                    Verifier MCP server (verify_task + assess_tests)
│   ├── src/
│   │   ├── server.ts                Two-tool MCP server
│   │   ├── index.ts                 Entry point with stdio transport
│   │   └── tools/
│   │       ├── verify-task.ts       Task verification via Claude Agent SDK
│   │       └── assess-tests.ts      Test quality assessment via Claude Agent SDK
│   └── dist/index.js                Built MCP entry point
├── agents/                          10 agent definitions (.md with frontmatter)
├── bin/
│   ├── install.js                   Plugin installer (npx gatekeeper)
│   ├── install-lib.js               Installer library (copy, verify, setup)
│   ├── opencode-mcp.sh              OpenCode MCP launcher (auto-clone/build)
│   └── verifier-mcp.sh              Verifier MCP launcher (auto-build)
├── commands/                        11 slash commands
├── hooks/
│   ├── hooks.json                   Hook event registration
│   ├── stop-hook.sh                 VGL loop control + auto-transition
│   ├── guard-scope.sh               File access restriction during VGL
│   ├── guard-plan.sh                Plan file lock during execution
│   ├── guard-orchestrator.sh        Orchestrator write restriction
│   ├── guard-skills.sh              Skill blocker during VGL
│   ├── post-cross.sh                Post-execution info
│   ├── intel-index.js               Codebase intelligence indexer (source)
│   └── dist/intel-index.js          Bundled indexer (built via esbuild)
├── scripts/
│   ├── bootstrap.sh                 Full installation script
│   ├── setup-verifier-loop.sh       Initialize VGL state
│   ├── generate-verifier-prompt.sh  Build immutable verifier prompt
│   ├── generate-test-assessor-prompt.sh  Build test assessor prompt
│   ├── fetch-completion-token.sh    Independent test execution for token
│   ├── transition-task.sh           Mark complete + find next task
│   ├── cross-team-setup.sh          Plan validation + task dispatch setup
│   ├── single-task-setup.sh         Single-task VGL setup
│   ├── validate-plan.py             Plan.yaml structural validation
│   ├── plan_utils.py                Shared plan utilities (load, save, find, sort)
│   ├── get-unblocked-tasks.py       Find all unblocked tasks
│   ├── check-file-conflicts.py      Detect file scope overlaps
│   ├── next-task.py                 Find next unblocked task
│   ├── parse-args.py                Argument parser for /bridge
│   ├── build-hooks.js               esbuild bundler for hook scripts
│   ├── evo_db.py                    MAP-Elites population database
│   ├── evo_eval.py                  Cascade evaluation
│   ├── evo_prompt.py                Evolutionary prompt construction
│   ├── evo_pollinator.py            Cross-task strategy pollination
│   ├── resilience.py                Circuit breaker / stuck detection
│   ├── run_history.py               Execution history tracking
│   ├── onboarding.sh                First-run onboarding
│   └── team-orchestrator-prompt.md  Lead orchestrator template
├── templates/
│   ├── opencode.json                gsd-builder agent + Context7 MCP config
│   ├── task-prompt.md               task-{id}.md template
│   ├── plan-summary.md              Plan summary template
│   └── codebase/                    7-dimension codebase analysis templates
├── references/                      Workflow reference docs
└── workflows/                       Phase workflow definitions
```

## Troubleshooting

### MCP servers not showing in `/mcp`

1. Restart Claude Code after installing the plugin
2. Check that both MCP server launchers are executable: `chmod +x bin/opencode-mcp.sh bin/verifier-mcp.sh`
3. Check that `plugin.json` declares both servers under `mcpServers`
4. Run the launchers manually to check for errors: `bash bin/verifier-mcp.sh`

### opencode agents fail to spawn

1. Verify opencode is installed: `opencode version`
2. Check that `opencode.json` exists in your project root (deployed automatically by cross-team setup)
3. Check the opencode binary path in `Better-OpenCodeMCP/src/constants.ts`

### Hook errors

1. Hooks require `jq` for JSON parsing: `jq --version`
2. All `.sh` files must be executable: `find . -name "*.sh" -exec chmod +x {} \;`
3. Check hook debug log: `cat /tmp/gatekeeper-stop-hook.debug.log`

### Build failures

```bash
# Rebuild everything from scratch
cd Better-OpenCodeMCP && rm -rf node_modules dist && npm install && npm run build && cd ..
cd verifier-mcp && rm -rf node_modules dist && npm install && npm run build && cd ..
npm install && npm run build:hooks
```

## Acknowledgments

Gatekeeper builds on ideas and infrastructure from [TÂCHES](https://github.com/gsd-build/get-shit-done), a spec-driven development system for Claude Code. The evolutionary superphase is inspired by [OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve), an open-source implementation of AlphaEvolve-style LLM-driven code optimization.

## License

MIT
