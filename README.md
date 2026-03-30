# Gatekeeper

> **Beta** — Gatekeeper is under active development. Expect breaking changes.

A Claude Code plugin for spec-driven development with cryptographic verifier loops, TDD-first execution, and concurrent opencode agents.

## How It Works

Gatekeeper orchestrates software projects through a structured pipeline where no task can be marked complete without passing independent verification:

1. **Plan** (`/quest`) -- Deep discovery + plan.yaml with phases, tasks, must_haves, TDD test specs, and per-task prompt files
2. **Assess Phase** -- Phase assessor creates format contracts (API shapes, data structures, wiring) so independently-written tests produce compatible interfaces
3. **Test** -- Tester agent researches the domain (WebSearch + Context7), writes comprehensive tests following format contracts, passes assessor quality gate (TQG token)
4. **Execute** (`/cross-team`) -- TDD-first implementation with parallel opencode agents, wave-based dispatch, and session continuations
5. **Verify** -- Independent verifier in a fresh context checks tests, inspects code, and runs Playwright visual verification. A 128-bit cryptographic Gatekeeper token is issued only on full pass
6. **Verify Phase** -- Phase verifier checks integration contracts, cross-phase wiring, and end-to-end data flows. PVG token gates the next phase
7. **Iterate** -- Failed verifications loop back through execution with evolutionary intelligence informing retry strategies

## Prerequisites

| Dependency | Minimum Version | Purpose |
|------------|----------------|---------|
| **Node.js** | >= 18.0.0 | MCP servers, hook scripts, installer |
| **npm** | (bundled with Node) | Package management |
| **Python 3** | >= 3.8 | Plan utilities, evolution engine, validation |
| **git** | any recent | Cloning, submodules |
| **jq** | any recent | JSON parsing in hook scripts |
| **Claude Code** | latest | The CLI tool that runs the plugin |
| **OpenCode** | latest | Agent dispatch for gk-builder agents |
| **ANTHROPIC_API_KEY** | -- | Auto-detected from subscription or set manually (see below) |

### Authentication

Assessor and verifier agents are spawned as Claude Code Task subagents. Authentication is resolved automatically:

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

The bootstrap script checks prerequisites, builds the MCP servers, installs the plugin to Claude Code, and verifies the installation.

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

#### 5. Install the Evolve MCP server dependencies

```bash
pip install fastmcp
```

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
- `plugin:gatekeeper:evolve-mcp` -- tools: `population_sample`, `evaluate_timing`, `profile_hotspots`, etc.

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
pip install fastmcp  # for evolve-mcp

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

### System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER COMMANDS                                  │
│  /quest          /cross-team        /hyperphase                             │
│  (planning)      (execution)        (optimization)                         │
└──────┬──────────────┬───────────────────┬──────────────────────────────────-─┘
       │              │                   │
       ▼              ▼                   ▼
┌─────────────┐ ┌───────────────┐ ┌─────────────────┐
│  PLANNING   │ │  HYPERPHASE 1 │ │  HYPERPHASE N   │
│  PIPELINE   │ │  Gatekeeper   │ │  Evo Optimize   │
│  (/quest)   │ │  (/cross-team)│ │  (/hyperphase)  │
└──────┬──────┘ └──────┬────────┘ └───────┬─────────┘
       │               │                  │
       ▼               ▼                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MCP SERVERS                                       │
│                                                                             │
│  opencode-mcp (Better-OpenCodeMCP)       evolve-mcp (FastMCP Python)        │
│  ├─ launch_opencode(task/sessionId)      ├─ population_{sample,add,best,    │
│  ├─ wait_for_completion(taskIds)         │   stats,migrate}                 │
│  └─ opencode_sessions(status)            ├─ evolution_prompt                │
│                                          ├─ evaluate_{correctness,timing}   │
│                                          ├─ profile_hotspots               │
│                                          ├─ {extract,replace,revert}_       │
│                                          │   function, apply_diff           │
│                                          └─ check_novelty                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                         SECURITY LAYER (4 Guards)                           │
│  guard-scope.sh ── blocks agent access to tokens, prompts, plugin source   │
│  guard-plan.sh  ── locks plan.yaml + task files during execution           │
│  guard-orchestrator.sh ── blocks orchestrator from writing code            │
│  guard-skills.sh ── blocks plan-modifying commands during Gatekeeper loop   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Planning Pipeline (`/quest`)

```
/quest
  │
  ▼
Phase 0 ── Gather Project Description
  │         Deep Discovery interview OR quick 1-3 sentence prompt
  ▼
Phase 1 ── Silent Codebase Reconnaissance
  │         Scan manifests, frameworks, DBs, auth, tests, env
  │         If brownfield (10+ source files): auto-spawn codebase-mapper
  ▼
Phase 2 ── Interactive Questioning
  │         Ask 3-8 questions about unknowns from recon
  ▼
Phase 3 ── Parallel Research
  │         Spawn 2-5 project-researcher agents (sonnet, WebSearch)
  │         Synthesize into Pre-flight Check
  ▼
Phase 4 ── Hierarchical Plan Generation
  │
  │   ┌──────────────────────┐
  │   │ high-level-planner   │ opus ── phases, must_haves, dependencies
  │   └──────────┬───────────┘
  │              ▼
  │   ┌──────────────────────┐
  │   │ plan-refiner (x2-3)  │ opus ── 7-dimension iterative improvement
  │   └──────────┬───────────┘
  │              ▼
  │   ┌──────────────────────┐
  │   │ phase-planner        │ opus ── one per phase, SEQUENTIAL
  │   │ (full prior context) │        each receives ALL prior phases + tasks
  │   └──────────┬───────────┘
  │              ▼
  │   ┌──────────────────────┐
  │   │ plan-checker         │ sonnet ── 6-dimension QA gate
  │   └──────────┬───────────┘
  │              ▼
  │   Output: plan.yaml + tasks/task-{id}.md + plan-summary.md
  ▼
Phase 5 ── Confirm & Summarize → "Run /cross-team to start execution"
```

### Hyperphase 1 — Gatekeeper TDD (`/cross-team`)

```
/cross-team
  │
  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                    LEAD ORCHESTRATOR (sonnet)                            │
│                    Never writes code. Coordinates workers.               │
│                    Only agent that updates plan.yaml.                    │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   Phase 0.5 ── PHASE ASSESSOR (opus, write access for specs only)       │
│   ┌─────────────────────────────────────────────────────────────────┐    │
│   │  Reads all task specs for the phase                             │    │
│   │  Creates format contracts:                                      │    │
│   │    contracts/api-contracts.md ── endpoint shapes                 │    │
│   │    contracts/data-contracts.md ── shared data structures         │    │
│   │    contracts/wiring-contracts.md ── component connection map     │    │
│   │    integration-test-spec.md ── integration test specifications   │    │
│   │    tester-guidance-task-{id}.md ── per-task format guidance      │    │
│   │                                                                 │    │
│   │  Output: PHASE_ASSESSMENT_PASS:{phase_id}:{summary}             │    │
│   │      or: PHASE_ASSESSMENT_FAIL:{phase_id}:{issues}              │    │
│   └──────────────────────┬──────────────────────────────────────────┘    │
│                          ▼                                               │
│   Orchestrator generates PAG_COMPLETE_{32_hex} token                     │
│                          ▼                                               │
│   For each unblocked task (parallel when file_scope doesn't overlap):    │
│                                                                          │
│   ┌─────────────────────────────────────────────────────────────────┐    │
│   │ Phase 1 ── TESTER (sonnet, web access)                         │    │
│   │                                                                 │    │
│   │  Receives format contracts from phase assessor                  │    │
│   │  WebSearch ──► domain research                                  │    │
│   │  Context7  ──► library API docs                                 │    │
│   │  Write tests ──► confirm TDD Red (tests fail)                   │    │
│   │                                                                 │    │
│   │  Output: TESTS_WRITTEN:{task_id}                                │    │
│   └──────────────────────┬──────────────────────────────────────────┘    │
│                          ▼                                               │
│   ┌─────────────────────────────────────────────────────────────────┐    │
│   │ Phase 1.5 ── ASSESSOR (opus, read-only)          max 10 rounds  │    │
│   │                                                   ┌──────────┐ │    │
│   │  Possibility ──► contradictions? impossible?      │ on FAIL: │ │    │
│   │  Comprehensiveness ──► happy/error/edge covered?  │ re-spawn │ │    │
│   │  Quality ──► realistic data? meaningful asserts?  │ tester   │ │    │
│   │  Alignment ──► every must_have has a test?        │ w/critic │ │    │
│   │  Format contracts ──► matches phase assessor?     └────┬─────┘ │    │
│   │                                                        │       │    │
│   │  Output: ASSESSMENT_PASS:{tqg_token}:{summary}         │       │    │
│   │      or: ASSESSMENT_FAIL:{issues} ─────────────────────┘       │    │
│   └──────────────────────┬──────────────────────────────────────────┘    │
│                          ▼                                               │
│   Orchestrator writes TQG token to assessor-token.secret                 │
│                          ▼                                               │
│   ┌─────────────────────────────────────────────────────────────────┐    │
│   │ Phase 2 ── EXECUTOR (haiku, no web)                             │    │
│   │                                                                 │    │
│   │  Read pre-written tests ──► parse Test Dependency Graph         │    │
│   │                                                                 │    │
│   │  Wave 1:  ┌──────────┐ ┌──────────┐ ┌──────────┐              │    │
│   │           │gk-builder│ │gk-builder│ │gk-builder│  concurrent │    │
│   │           │ T1 (new)  │ │ T2 (new)  │ │ T3 (new)  │             │    │
│   │           └─────┬─────┘ └─────┬─────┘ └─────┬─────┘             │    │
│   │                 └──────┬──────┘──────────────┘                   │    │
│   │                        ▼                                         │    │
│   │           wait_for_completion() ──► record sessionIds            │    │
│   │                        ▼                                         │    │
│   │  Wave 2+: ┌──────────────────┐ ┌──────────────────┐            │    │
│   │           │gk-builder T4    │ │gk-builder T5    │  continue   │    │
│   │           │(continue T1 sess)│ │(continue T2 sess)│  sessions   │    │
│   │           └──────────────────┘ └──────────────────┘             │    │
│   │                                                                 │    │
│   │  Run full test suite ──► TDD Green                              │    │
│   │                                                                 │    │
│   │  Output: IMPLEMENTATION_READY:{task_id}                         │    │
│   └──────────────────────┬──────────────────────────────────────────┘    │
│                          ▼                                               │
│   ┌─────────────────────────────────────────────────────────────────┐    │
│   │ Phase 2.5 ── VERIFIER (opus, read-only)          max 10 rounds  │    │
│   │                                                   ┌──────────┐ │    │
│   │  16-point deep inspection:                        │ on FAIL: │ │    │
│   │   empty bodies, hardcoded returns, TODOs,         │ test_iss │ │    │
│   │   dead code, silent catches, fake data,           │  → tester│ │    │
│   │   type casts, missing imports, SQL inject,        │ impl_iss │ │    │
│   │   hardcoded secrets, no error handling,           │  → exec  │ │    │
│   │   infinite loops, race conditions, leaks,         └────┬─────┘ │    │
│   │   security vulns                                       │       │    │
│   │  Run tests independently                               │       │    │
│   │  Verify must_haves (truths, artifacts, key_links)      │       │    │
│   │  Playwright visual check (if dev_server_url)           │       │    │
│   │                                                         │       │    │
│   │  Output: VERIFICATION_PASS                              │       │    │
│   │      or: VERIFICATION_FAIL:{category,critique} ────────┘       │    │
│   └──────────────────────┬──────────────────────────────────────────┘    │
│                          ▼                                               │
│   ┌─────────────────────────────────────────────────────────────────┐    │
│   │ Token Generation & Task Completion                               │    │
│   │                                                                  │    │
│   │  token = openssl rand -hex 32 | head -c 32                      │    │
│   │  gk_token = "GK_COMPLETE_{token}"                               │    │
│   │  Write to .claude/gk-sessions/task-{id}/verifier-token.secret   │    │
│   │  plan_utils.py --complete-task {task_id} --token {gk_token}      │    │
│   └──────────────────────┬──────────────────────────────────────────┘    │
│                          ▼                                               │
│   ┌─────────────────────────────────────────────────────────────────┐    │
│   │ Phase Verification Gate (when last task in phase completes)      │    │
│   │                                                                  │    │
│   │ PHASE VERIFIER (opus, read-only)                                 │    │
│   │  Reads integration specs from phase assessor                     │    │
│   │  Verifies contract compliance (API, data, wiring)                │    │
│   │  Runs integration tests from spec                                │    │
│   │  Checks cross-phase wiring + end-to-end data flow                │    │
│   │                                                                  │    │
│   │  Output: PHASE_VERIFICATION_PASS:{phase_id}                      │    │
│   │      or: PHASE_VERIFICATION_FAIL:{phase_id}:{critique}           │    │
│   │                                                                  │    │
│   │  On PASS: orchestrator generates PVG_COMPLETE_{32_hex} token     │    │
│   └──────────────────────┬──────────────────────────────────────────┘    │
│                          ▼                                               │
│   Newly unblocked tasks? ──► next phase starts at Phase 0.5             │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### Hyperphase N — Evolutionary Optimization (`/hyperphase`)

```
All Hyperphase 1 tasks VERIFICATION_PASS  +  metadata.hyperphase: true
  │
  ▼
Phase S1 ── Scout Identification (parallel per module)
  │
  │  ┌────────────┐ ┌────────────┐ ┌────────────┐
  │  │ evo-scout  │ │ evo-scout  │ │ evo-scout  │  haiku, parallel
  │  │ module A   │ │ module B   │ │ module C   │
  │  │ cProfile   │ │ cProfile   │ │ cProfile   │
  │  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
  │        └───────────┬───┘──────────────┘
  │                    ▼
  │  Rank by score = time_pct × log(1 + complexity)
  │  Filter: complexity > 5, test_count >= 1
  │  Select top K candidates (default 3)
  │
  ▼
Phase S2 ── Island Optimization (sequential per candidate, parallel islands)
  │
  │  For each candidate function:
  │
  │  evolve-mcp::extract_function ──► mark with EVOLVE-BLOCK-START/END
  │
  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
  │  │ Island 0     │ │ Island 1     │ │ Island 2     │ │ Island 3     │ │ Island 4     │
  │  │ haiku        │ │ haiku        │ │ haiku        │ │ haiku        │ │ opus         │
  │  │ vectorize    │ │ reduce-alloc │ │ memoize      │ │ data-struct  │ │ novel-algo   │
  │  │ numpy, list  │ │ in-place,    │ │ precompute,  │ │ set, deque,  │ │ O(n²)→O(n),  │
  │  │ comprehens.  │ │ generators   │ │ cache        │ │ array layout │ │ math reform  │
  │  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
  │         │                │                │                │                │
  │         │  Each island runs up to 15 iterations:                            │
  │         │  population_sample → evolution_prompt → generate diff →           │
  │         │  apply_diff → evaluate_correctness → evaluate_timing →            │
  │         │  check_novelty → population_add                                   │
  │         │  (patience=5, early stop if speedup >= 1.5)                       │
  │         │                │                │                │                │
  │         └────────────────┼────────────────┼────────────────┼────────────────┘
  │                          ▼
  │  Ring migration:  0 → 1 → 2 → 3 → 4 → 0
  │  population_best ──► select global winner
  │  If speedup >= 1.3: replace_function (backup original)
  │
  ▼
Phase S3 ── Final Verification
  │
  │  Run full test suite
  │  PASS ──► write hyperphase-results.md (per-function speedup table)
  │  FAIL ──► revert_function for ALL patched files, re-test, report
  │
  ▼
Done. Results in hyperphase-results.md
```

### Agent Roster

```
┌────────────────────┬────────┬─────────┬──────────────────────────────────────────────┐
│ Agent              │ Model  │ Color   │ Role                                         │
├────────────────────┼────────┼─────────┼──────────────────────────────────────────────┤
│                    │        │         │                                              │
│ PLANNING AGENTS    │        │         │                                              │
│ high-level-planner │ opus   │ green   │ Phase outline from discovery + recon         │
│ plan-refiner       │ opus   │ green   │ 7-dimension iterative outline improvement    │
│ phase-planner      │ opus   │ green   │ Decompose 1 phase into tasks + TDD specs    │
│ planner (legacy)   │ opus   │ green   │ Monolithic plan generation (alternative)     │
│ plan-checker       │ sonnet │ green   │ Pre-execution 6-dimension QA gate            │
│                    │        │         │                                              │
│ HYPERPHASE 1       │        │         │                                              │
│ phase-assessor     │ opus   │ magenta │ Pre-phase format contracts + tester guidance  │
│ tester             │ sonnet │ cyan    │ Research + write tests (TDD Red)             │
│ assessor           │ opus   │ magenta │ Test quality gate + TQG token (read-only)    │
│ executor           │ haiku  │ yellow  │ TDD implementation via opencode agents       │
│ verifier           │ opus   │ green   │ 16-point code inspection (read-only)         │
│ phase-verifier     │ opus   │ green   │ Phase-end integration verification + PVG     │
│                    │        │         │                                              │
│ HYPERPHASE N       │        │         │                                              │
│ evo-scout          │ haiku  │ cyan    │ cProfile hotspot identification              │
│ evo-optimizer      │ haiku* │ magenta │ Island-based speed optimization              │
│                    │        │         │ *island 4 uses opus                          │
│                    │        │         │                                              │
│ SUPPORT AGENTS     │        │         │                                              │
│ project-researcher │ sonnet │ blue    │ Domain research (WebSearch)                  │
│ phase-researcher   │ sonnet │ blue    │ Phase-specific technical deep dives          │
│ codebase-mapper    │ sonnet │ blue    │ 7-dimension brownfield analysis              │
│ debugger           │ sonnet │ red     │ Scientific method debugging                  │
└────────────────────┴────────┴─────────┴──────────────────────────────────────────────┘
```

### Signal Flow

```
Phase Assessor ── PHASE_ASSESSMENT_PASS:{phase_id}:{summary} ──► generate PAG token, spawn Testers
               └─ PHASE_ASSESSMENT_FAIL:{phase_id}:{issues} ──► fix and retry

Tester ─── TESTS_WRITTEN:{id} ───────────────► Orchestrator ──► spawn Assessor
       └── TESTS_WRITE_FAILED:{id}:{reason} ──► log, skip

Assessor ── ASSESSMENT_PASS:{tqg_token}:{summary} ──► write TQG token, spawn Executor
         └─ ASSESSMENT_FAIL:{issues} ────────────────► re-spawn Tester (max 10)

Executor ── IMPLEMENTATION_READY:{id} ────────► Orchestrator ──► spawn Verifier
         └─ TASK_FAILED:{id}:{reason} ────────► log, retry or skip

Verifier ── VERIFICATION_PASS ────────────────► generate GK token, mark complete
         └─ VERIFICATION_FAIL:{critique} ────► test_issue: re-spawn Tester (reassess)
                                               impl_issue: re-spawn Executor (max 10)

Phase Verifier ── PHASE_VERIFICATION_PASS:{phase_id} ──► generate PVG token, next phase
               └─ PHASE_VERIFICATION_FAIL:{phase_id}:{critique} ──► fix CRITICAL issues

Evo-scout ── SCOUT_DONE:{module}:{json} ─────► rank, select top-K

Evo-optimizer ── OPTIMIZATION_PASS:{island}:{speedup}:{iter} ──► migration + patching
              └─ OPTIMIZATION_SKIP:{island}:{reason} ──────────► skip candidate
```

### Security Model

```
┌─────────────────────────────────────────────────────────────────┐
│                      4-LAYER GUARD SYSTEM                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  guard-scope.sh (PreToolUse: Read/Bash/Grep/Glob)               │
│  ├─ Blocks: *-token.secret, *-prompt.local.md                   │
│  ├─ Blocks: .claude/plugins/, agents/*.md, hooks/, commands/    │
│  └─ Active when: .claude/verifier-loop.local.md exists          │
│                                                                 │
│  guard-plan.sh (PreToolUse: Write/Edit)                         │
│  ├─ Blocks: .claude/plan/plan.yaml, .claude/plan/tasks/*        │
│  └─ Active when: .claude/plan-locked exists                     │
│                                                                 │
│  guard-orchestrator.sh (PreToolUse: Write/Edit/WebFetch/Search) │
│  ├─ Blocks: ALL 4 tools (orchestrator can't write code)         │
│  └─ Active when: .claude/gk-team-active exists                 │
│                                                                 │
│  guard-skills.sh (PreToolUse: Skill)                            │
│  ├─ Blocks: all /gatekeeper:* except /cross-team                │
│  └─ Active when: .claude/verifier-loop.local.md exists          │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  CRYPTOGRAPHIC TOKEN CHAIN (6 gates: 2 planning + 4 execution)   │
│                                                                 │
│  ── PLANNING TOKENS (issued during /quest) ──                    │
│                                                                 │
│  TPG ── Task Plan Gate                                           │
│  ├─ Format: TPG_COMPLETE_{32_hex_chars} (128-bit)               │
│  ├─ Generated: by task-plan-assessor agent per task-*.md file   │
│  └─ Stored: completion_tokens table via MCP submit_token         │
│                                                                 │
│  PPG ── Phase Plan Gate                                          │
│  ├─ Format: PPG_COMPLETE_{32_hex_chars} (128-bit)               │
│  ├─ Generated: by orchestrator after PHASE_PLAN_PASS            │
│  └─ Stored: phase_tokens table via MCP submit_ppg_token          │
│                                                                 │
│  ── EXECUTION TOKENS (issued during /cross-team) ──              │
│                                                                 │
│  PAG ── Phase Assessment Gate                                   │
│  ├─ Format: PAG_COMPLETE_{32_hex_chars} (128-bit)               │
│  ├─ Generated: by orchestrator after PHASE_ASSESSMENT_PASS      │
│  └─ Stored: .claude/gk-sessions/phase-{id}/pag-token.secret    │
│                                                                 │
│  TQG ── Test Quality Gate                                       │
│  ├─ Format: TQG_COMPLETE_{32_hex_chars} (128-bit)               │
│  ├─ Generated: by assessor agent, included in ASSESSMENT_PASS   │
│  └─ Stored: .claude/gk-sessions/task-{id}/assessor-token.secret│
│                                                                 │
│  GK ── Gatekeeper loop                                      │
│  ├─ Format: GK_COMPLETE_{32_hex_chars} (128-bit)               │
│  ├─ Generated: by orchestrator after VERIFICATION_PASS          │
│  ├─ Stored: .claude/gk-sessions/task-{id}/verifier-token.secret│
│  └─ Validated: plan_utils.py --complete-task --token             │
│                                                                 │
│  PVG ── Phase Verification Gate                                  │
│  ├─ Format: PVG_COMPLETE_{32_hex_chars} (128-bit)               │
│  ├─ Generated: by orchestrator after PHASE_VERIFICATION_PASS    │
│  └─ Stored: .claude/gk-sessions/phase-{id}/pvg-token.secret    │
│                                                                 │
│  Planning chain: TPG (per task) → PPG (per phase)                │
│  Execution chain: PAG → TQG → GK → PVG                          │
└─────────────────────────────────────────────────────────────────┘
```

### Data Layout

```
project/
├── .claude/
│   ├── plan/
│   │   ├── plan.yaml                    Phases, tasks, dependencies, must_haves
│   │   ├── high-level-outline.yaml      Phase-level plan (planner output)
│   │   └── tasks/
│   │       ├── task-1.1.md              Per-task prompt with TDD specs + guidance
│   │       └── task-1.2.md
│   ├── plans/
│   │   └── plan-summary.md             Condensed plan overview
│   ├── gk-sessions/                   Per-task/phase Gatekeeper state (during execution)
│   │   ├── phase-1/
│   │   │   ├── pag-token.secret        PAG token (phase assessment gate)
│   │   │   ├── pvg-token.secret        PVG token (phase verification gate)
│   │   │   └── integration-specs/      Format contracts from phase assessor
│   │   │       ├── contracts/
│   │   │       │   ├── api-contracts.md
│   │   │       │   ├── data-contracts.md
│   │   │       │   └── wiring-contracts.md
│   │   │       ├── integration-test-spec.md
│   │   │       └── tester-guidance-task-{id}.md
│   │   └── task-1.1/
│   │       ├── verifier-token.secret   GK token (task verification)
│   │       ├── assessor-token.secret   TQG token (test quality gate)
│   │       └── state.md                Session state
│   ├── gk-team-active                 Marker: team orchestration running
│   └── plan-locked                     Marker: plan files locked
├── .planning/
│   ├── PROJECT.md                      Intent anchor for all subagents
│   ├── STATE.md                        Current project state
│   ├── config.json                     Planning configuration
│   ├── codebase/                       7-dimension brownfield analysis
│   │   ├── STACK.md, ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md
│   │   ├── TESTING.md, INTEGRATIONS.md, CONCERNS.md
│   ├── evolution/                      MAP-Elites populations
│   │   ├── {task_id}/                  Per-task evolution DB (Hyperphase 1 retries)
│   │   └── hyperphase/{function}/      Per-function DB (Hyperphase N)
│   └── debug/{slug}.md                 Persistent debug state
└── opencode.json                       gk-builder agent config (deployed at setup)

gatekeeper/                             Plugin directory
├── .claude-plugin/
│   └── plugin.json                     MCP servers: opencode-mcp, evolve-mcp
├── agents/           (17)              Agent definitions (.md with frontmatter)
├── commands/         (11)              Slash commands
├── hooks/            (7)               Event hooks + hooks.json
├── scripts/          (23)              CLI tools, setup scripts, evo engine
├── evolve-mcp/                         FastMCP Python server (16 tools)
├── Better-OpenCodeMCP/                 Submodule: opencode agent dispatch
├── templates/                          opencode.json, task-prompt.md, codebase/
├── references/                         Model profiles, workflow docs
└── workflows/                          Phase workflow definitions
```

## Core Concepts

### Gatekeeper Loop (GK)

The executor cannot complete a task. Only the verifier can, and it runs in an independent context. The orchestrator generates a 128-bit cryptographic token (`GK_COMPLETE_[32-hex]`) only when the verifier returns `VERIFICATION_PASS` after all checks:

- 16-point deep code inspection passes (no stubs, TODOs, fakes, security issues)
- Tests pass in an independent subprocess
- Must_haves truths, artifacts, and key_links are satisfied
- Playwright visual verification passes (if dev_server_url configured)

The token is written to `verifier-token.secret` and validated by `plan_utils.py --complete-task`. No valid token = task stays incomplete.

### Test Quality Gate (Assessor + TQG Token)

Before implementation begins, the tester agent's tests must pass an independent opus-level assessment:

- Are tests internally consistent (no contradictions)?
- Do they cover happy paths, error paths, edge cases, and boundaries?
- Is every must_have represented by test assertions?
- Are assertions meaningful (not trivial `expect(true)`)?
- Is test data realistic (not "foo", "bar")?
- Do tests comply with format contracts from the phase assessor?

On pass, the assessor generates a cryptographic TQG token (`TQG_COMPLETE_[32-hex]`) included in its output signal. The orchestrator extracts and stores it in `assessor-token.secret`. On fail, tests are iteratively fixed (max 10 rounds).

### TDD-First with Wave Dispatch

Every task follows: write tests first (tester), assess (assessor), implement (executor), verify (verifier).

Implementation uses a **Test Dependency Graph** from the task prompt:

```
| Test | File              | Depends On | Guidance                          |
|------|-------------------|------------|-----------------------------------|
| T1   | tests/auth.test   | -          | Create auth module, use bcrypt    |
| T2   | tests/api.test    | -          | Create API routes, mock DB        |
| T3   | tests/flow.test   | T1, T2     | Wire auth into API, test e2e      |
```

- **Wave 1**: T1 and T2 launch as fresh gk-builder opencode agents (concurrent)
- **Wave 2**: T3 continues T2's session (most significant dependency) and reviews T1's work
- Each agent gets exactly 1 test + specific implementation guidance
- `wait_for_completion()` after each wave; handle `input_required` questions via session continuation

### Goal-Backward Must-Haves

Verification checks three levels derived from the project goal:

- **Truths** -- User-observable behaviors that must work ("User can log in and see dashboard")
- **Artifacts** -- Files with real implementation, not stubs ("src/auth/route.ts exports POST handler")
- **Key Links** -- Critical connections between components ("Login form POST /api/auth -> session cookie -> dashboard reads session")

### Phase Gates (Assessor + Verifier)

Each phase is bookended by two phase-level gates:

**Phase Assessor** (start of phase): Before testers run, a phase assessor reads all task specs and creates format contracts — API shapes, shared data structures, wiring maps, and per-task tester guidance. This ensures independently-written tests produce compatible interfaces.

**Phase Verifier** (end of phase): When all tasks in a phase with `integration_check: true` pass verification, a phase verifier checks that integration contracts are satisfied, cross-phase wiring is intact, and end-to-end data flows work. Issues are categorized as CRITICAL (blocks next phase) or WARNING (can proceed).

### Evolutionary Intelligence

Gatekeeper uses an evolutionary approach to improve strategies across iterations and tasks:

- **MAP-Elites Population Database** (`evo_db.py`) -- Stores diverse approaches in a multi-dimensional grid indexed by island and behavioral descriptors
- **Island-Based Parallel Exploration** -- On retry iterations with sufficient population (>= 3 approaches), the executor samples strategies from different islands and spawns parallel agents
- **Cascade Evaluation** (`evo_eval.py`) -- Each attempt is evaluated on multiple dimensions (test pass rate, duration, complexity, speedup ratio)
- **Evolutionary Prompt Construction** (`evo_prompt.py`) -- Builds context-aware prompts from the population, surfacing best strategies and common failure patterns. Speed mode cycles 7 optimization directives
- **Cross-Task Pollination** (`evo_pollinator.py`) -- Successful strategies from similar completed tasks are migrated into new task populations

### Plan Format

```yaml
metadata:
  project: "Project Name"
  dev_server_command: "npm run dev"
  test_framework: "vitest"
  hyperphase: true                # opt-in for Hyperphase N
  hyperphase_candidates: 3        # top-K hotspots to optimize

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
| `/quest` | Plan a project -- 5-phase discovery that generates plan.yaml + task prompt files |
| `/cross-team` | Hyperphase 1 -- execute tasks with TDD + Gatekeeper loop (parallel team orchestration) |
| `/hyperphase` | Hyperphase N -- evolutionary optimization of hot-spot functions after verification |
| `/research` | Domain research before planning (parallel researcher agents) |
| `/map-codebase` | Analyze existing codebase (7-dimension brownfield analysis) |
| `/settings` | Configure model profiles and preferences |
| `/run-away` | Cancel the active Gatekeeper loop |
| `/help` | Command reference |

## Agents

| Agent | Role | Model | Key Tools |
|-------|------|-------|-----------|
| **Hyperphase 1** | | | |
| `phase-assessor` | Pre-phase format contracts + tester guidance (PAG token) | opus | Read, Write, Edit, Bash, Grep, Glob |
| `tester` | Researches domain, writes comprehensive tests (TDD Red) | sonnet | WebSearch, WebFetch, Context7 |
| `assessor` | Test quality gate + TQG token -- possibility, comprehensiveness, format compliance | opus | Read, Bash, Grep, Glob (read-only) |
| `executor` | TDD-first implementation via parallel gk-builder opencode agents | haiku | opencode MCP, Context7 |
| `verifier` | 16-point code inspection, must_haves verification, Playwright | opus | Read, Bash, Grep, Glob (read-only) |
| `phase-verifier` | Phase-end integration verification + PVG token | opus | Read, Bash, Grep, Glob (read-only) |
| **Planning** | | | |
| `high-level-planner` | Designs phase outline from discovery + recon | opus | Read, Write, Bash |
| `plan-refiner` | 7-dimension iterative outline improvement | opus | Read, Write, Bash |
| `phase-planner` | Decomposes one phase into tasks + TDD specs (sequential, full prior context) | opus | Read, Write, Bash, WebFetch |
| `planner` (legacy) | Monolithic plan generation (alternative to hierarchical) | opus | Read, Write, Bash |
| `plan-checker` | Pre-execution plan quality gate (6 verification dimensions) | sonnet | Read, Bash, Grep, Glob |
| **Hyperphase N** | | | |
| `evo-scout` | cProfile hotspot identification | haiku | Read, Bash, evolve-mcp |
| `evo-optimizer` | Island-based speed optimization (5 parallel islands) | haiku/opus | Bash, evolve-mcp (all tools) |
| **Support** | | | |
| `project-researcher` | Domain research -- tech stacks, patterns, pitfalls | sonnet | WebSearch, WebFetch |
| `phase-researcher` | Phase-specific technical deep dives -- APIs, libraries | sonnet | WebSearch, WebFetch |
| `codebase-mapper` | Brownfield codebase analysis (7 dimensions) | sonnet | Read, Bash, Grep, Glob |
| `debugger` | Scientific method debugging with persistent state | sonnet | Read, Write, Edit, Bash |

### gk-builder (opencode agent)

The opencode MCP server spawns agents using the `gk-builder` profile defined in `templates/opencode.json`:

- No web access (websearch/webfetch disabled)
- **Context7 MCP server** for library documentation research
- Research-first prompt -- agents must look up APIs via Context7 before implementing
- Bash (ask permission), Edit/Write (allowed)
- Temperature 1.0, no step limit

```
templates/opencode.json          Canonical config (checked into gatekeeper repo)
       |
       v (copied at setup time by cross-team-setup.sh / setup-verifier-loop.sh)
<project>/opencode.json          Deployed to project root
       |
       v (opencode reads from cwd on spawn)
opencode run --agent gk-builder  Spawned by Better-OpenCodeMCP
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
| `stop-hook.sh` | Stop | Prevents exit during Gatekeeper loop. Validates token, auto-transitions to next task |
| `guard-scope.sh` | PreToolUse: Read, Bash, Grep, Glob | Blocks agent access to infrastructure files during Gatekeeper loop |
| `guard-plan.sh` | PreToolUse: Write, Edit | Locks plan.yaml and task files during execution |
| `guard-orchestrator.sh` | PreToolUse: Write, Edit, WebFetch, WebSearch | Blocks code-writing by the lead orchestrator in team mode |
| `guard-skills.sh` | PreToolUse: Skill | Blocks plan-modifying commands during active Gatekeeper loop |
| `post-cross.sh` | PostToolUse: Skill | Shows next task in pipeline after /cross-team |
| `intel-index.js` | PostToolUse: Write, Edit | Indexes file exports/imports for codebase intelligence |

## MCP Servers

### opencode-mcp (`plugin:gatekeeper:opencode-mcp`)

Agent dispatch via the OpenCode CLI. Source: `Better-OpenCodeMCP/`.

| Tool | Purpose |
|------|---------|
| `launch_opencode(task="...")` | Spawn a fresh gk-builder agent |
| `launch_opencode(sessionId="...", task="...")` | Continue an existing agent's session |
| `launch_opencode(tasks=[...])` | Batch-launch multiple agents |
| `wait_for_completion(taskIds=[...])` | Block until agents finish |
| `opencode_sessions(status="active")` | Check running agents |

### evolve-mcp (`plugin:gatekeeper:evolve-mcp`)

Evolutionary optimization engine for Hyperphase N. Source: `evolve-mcp/` (FastMCP Python).

| Tool | Purpose |
|------|---------|
| `population_sample(db_path, island_id)` | Sample a parent approach from MAP-Elites population |
| `population_add(db_path, approach_json)` | Add an evaluated approach to the population |
| `population_best(db_path)` | Return the globally best approach |
| `population_stats(db_path)` | Population statistics (size, coverage, per-island bests) |
| `population_migrate(db_path, src, dst)` | Ring-topology migration between islands |
| `evolution_prompt(db_path, task_id, island_id, mode)` | Build 5-section evolution context prompt |
| `evaluate_correctness(test_command)` | Cascade evaluator: test pass rate, duration, complexity |
| `evaluate_timing(test_command, function_name, ...)` | Time a function, compute speedup ratio vs baseline |
| `profile_hotspots(test_command, source_dirs)` | cProfile test suite, rank slow functions by score |
| `extract_function(file_path, function_name)` | Extract function with EVOLVE-BLOCK-START/END markers |
| `apply_diff(file_path, function_name, diff)` | Apply SEARCH/REPLACE diff to a function |
| `replace_function(file_path, function_name, new_code)` | Replace function body (creates .bak backup) |
| `revert_function(file_path, function_name)` | Restore function from most recent .bak backup |
| `check_novelty(candidate_code, reference_codes)` | Structural novelty heuristic score |

Both MCP servers auto-install dependencies on first launch via their launcher scripts in `bin/`.

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
├── evolve-mcp/                      FastMCP Python server (16 tools)
│   ├── server.py                    MCP tool definitions
│   └── requirements.txt             fastmcp dependency
├── agents/                          17 agent definitions (.md with frontmatter)
├── bin/
│   ├── install.js                   Plugin installer (npx gatekeeper)
│   ├── install-lib.js               Installer library (copy, verify, setup)
│   ├── opencode-mcp.sh              OpenCode MCP launcher (auto-clone/build)
│   └── evolve-mcp.sh               Evolve MCP launcher (auto-install fastmcp)
├── commands/                        12 slash commands
├── hooks/
│   ├── hooks.json                   Hook event registration
│   ├── stop-hook.sh                 Gatekeeper loop control + auto-transition
│   ├── guard-scope.sh               File access restriction during Gatekeeper loop
│   ├── guard-plan.sh                Plan file lock during execution
│   ├── guard-orchestrator.sh        Orchestrator write restriction
│   ├── guard-skills.sh              Skill blocker during Gatekeeper loop
│   ├── post-cross.sh                Post-execution info
│   ├── intel-index.js               Codebase intelligence indexer (source)
│   └── dist/intel-index.js          Bundled indexer (built via esbuild)
├── scripts/
│   ├── bootstrap.sh                 Full installation script
│   ├── setup-verifier-loop.sh       Initialize Gatekeeper state
│   ├── generate-verifier-prompt.sh  Build immutable verifier prompt
│   ├── generate-test-assessor-prompt.sh  Build test assessor prompt
│   ├── fetch-completion-token.sh    Independent test execution for token
│   ├── cross-team-setup.sh          Plan validation + task dispatch setup
│   ├── validate-plan.py             Plan.yaml structural validation
│   ├── plan_utils.py                Shared plan utilities (load, save, find, sort)
│   ├── get-unblocked-tasks.py       Find all unblocked tasks
│   ├── check-file-conflicts.py      Detect file scope overlaps
│   ├── next-task.py                 Find next unblocked task
│   ├── build-hooks.js               esbuild bundler for hook scripts
│   ├── evo_db.py                    MAP-Elites population database
│   ├── evo_eval.py                  Cascade evaluation + timing
│   ├── evo_prompt.py                Evolutionary prompt construction (general + speed modes)
│   ├── evo_block.py                 Function extraction, diff, replace, revert
│   ├── evo_profiler.py              cProfile hotspot profiler
│   ├── evo_pollinator.py            Cross-task strategy pollination
│   ├── resilience.py                Circuit breaker / stuck detection
│   ├── run_history.py               Execution history tracking
│   ├── onboarding.sh                First-run onboarding
│   └── team-orchestrator-prompt.md  Lead orchestrator template (Sections 0.5-8)
├── templates/
│   ├── opencode.json                gk-builder agent + Context7 MCP config
│   ├── task-prompt.md               task-{id}.md template
│   ├── plan-summary.md              Plan summary template
│   └── codebase/                    7-dimension codebase analysis templates
├── references/                      Workflow reference docs
└── workflows/                       Phase workflow definitions
```

## Troubleshooting

### MCP servers not showing in `/mcp`

1. Restart Claude Code after installing the plugin
2. Check that MCP server launchers are executable: `chmod +x bin/opencode-mcp.sh bin/evolve-mcp.sh`
3. Check that `plugin.json` declares both servers under `mcpServers`
4. Run the launchers manually to check for errors: `bash bin/evolve-mcp.sh`

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
npm install && npm run build:hooks
pip install fastmcp  # for evolve-mcp
```

## Acknowledgments

Gatekeeper builds on ideas and infrastructure from [TÂCHES](https://github.com/gsd-build/get-shit-done), a spec-driven development system for Claude Code. Hyperphase N (evolutionary optimization) is inspired by [OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve), an open-source implementation of AlphaEvolve-style LLM-driven code optimization.

## License

MIT
