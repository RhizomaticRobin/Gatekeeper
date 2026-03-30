# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Gatekeeper is a Claude Code plugin for spec-driven development with cryptographic verifier loops, TDD-first execution, and concurrent agent orchestration. It enforces a pipeline where no task can be marked complete without passing independent verification via 128-bit cryptographic tokens.

The project vision is evolving Gatekeeper into a self-improving, autonomously-learning development system — retaining cryptographic verification while adding adaptive orchestration and cross-project learning.

## Build & Test Commands

```bash
# Build hooks (compiles intel-index.js via esbuild)
npm run build:hooks

# Run Node.js tests (Vitest)
npx vitest run                          # all tests
npx vitest run tests/node/smoke.test.js # single test

# Run Bash tests (BATS)
npx bats tests/bash/smoke.bats          # single suite
npx bats tests/bash/*.bats              # all bash tests

# Run Python tests (pytest)
python3 -m pytest tests/python/                    # all python tests
python3 -m pytest tests/python/test_plan_utils.py  # single file
python3 -m pytest tests/python/test_evo_db.py -k "test_name" # single test

# E2E tests (BATS)
npx bats tests/e2e/smoke-test.bats

# Plan validation
python3 scripts/validate-plan.py plan.yaml
```

## Architecture

### Plugin System
- `.claude-plugin/plugin.json` — MCP server registrations and marketplace metadata
- `hooks/hooks.json` — PreToolUse/PostToolUse hooks with matchers (guard-scope, guard-plan, guard-orchestrator, guard-skills, guard-write-scope, stop-hook)
- `bin/install.js` / `bin/install-lib.js` — Plugin installer (registered as `npx gatekeeper`)

### Three Language Layers
- **Bash** (`scripts/*.sh`, `hooks/*.sh`) — Bootstrap, setup, guard hooks, token fetching, prompt generation
- **Python** (`scripts/*.py`, `gatekeeper-evolve-mcp/`) — Plan utilities, evolution engine, validation, MCP server
- **JavaScript/TypeScript** (`bin/`, `hooks/intel-index.js`, `verifier-mcp/`) — Installer, hook compilation, MCP server

### MCP Server: `evolve-mcp` (FastMCP Python)
Entry: `gatekeeper-evolve-mcp/src/gatekeeper_evolve_mcp/server.py`
Launch: `bin/gatekeeper-evolve-mcp.sh`
Database: SQLite with schema in `unified_schema.sql`

Tools organized in `tools/` subdirectory covering: sessions, tokens, signals, evolution (MAP-Elites population), profiling, function extraction/mutation, Taichi GPU analysis, formal verification (Kani, Prusti, CrossHair/Z3), phase gates, task encryption.

### Agent Definitions (`agents/`)
26 agent `.md` files with YAML frontmatter specifying `name`, `model` (opus/sonnet/haiku), `tools`, `disallowedTools`. Each agent has structured XML sections: `<role>`, `<input_format>`, `<output_format>`, `<deviation_rules>`.

Key agents in the execution pipeline:
- **phase-assessor** → creates format contracts, emits PAG token
- **tester** → writes tests (TDD Red), emits `TESTS_WRITTEN`
- **assessor** → validates test quality, emits TQG token
- **executor** → implements code (TDD Green), emits `IMPLEMENTATION_READY`
- **verifier** → 16-point code inspection, emits GK token
- **phase-verifier** → integration verification, emits PVG token

### Slash Commands (`commands/`)
- `/quest` — Planning pipeline (discovery, research, hierarchical plan generation)
- `/cross-team` — Hyperphase 1 execution (TDD gatekeeper loop with parallel agents)
- `/hyperphase` — Hyperphase N evolutionary optimization (MAP-Elites, island-based)
- `/hyperphase-plan` — Optimization candidate discovery before `/hyperphase`
- `/map-codebase` — Brownfield codebase analysis (7 dimensions)

### Cryptographic Token Pipeline
Six gate tokens, all 128-bit (`openssl rand -hex 32`), format `{PREFIX}_COMPLETE_{32hex}`:
- **TPG** (Task Plan Gate) / **PPG** (Phase Plan Gate) — planning verification
- **PAG** (Phase Assessment Gate) — phase assessor approval
- **TQG** (Test Quality Gate) — test assessor approval
- **GK** (Gatekeeper) — full verification pass
- **PVG** (Phase Verification Gate) — phase-level integration pass

### Guard Hooks (Security Model)
Hooks in `hooks/hooks.json` enforce isolation during execution:
- `guard-scope.sh` — blocks agents from reading `*-token.secret`, `*-prompt.local.md`, infrastructure files
- `guard-plan.sh` — locks `plan.yaml` and task files during execution (`.claude/plan-locked` marker)
- `guard-orchestrator.sh` — prevents orchestrator from writing code (`.claude/gk-team-active` marker)
- `guard-write-scope.sh` — validates writes stay within task's `file_scope.owns`
- `guard-skills.sh` — blocks plan-modifying commands during verifier loop

### Evolution Engine (`scripts/evo_*.py`)
- `evo_db.py` — MAP-Elites population database (multi-dimensional grid, behavioral descriptors)
- `evo_eval.py` — Cascade evaluation (test pass rate, duration, complexity, speedup)
- `evo_prompt.py` — Evolution context prompt builder (5-section, 7 optimization directives)
- `evo_block.py` — Function extraction with dependencies
- `evo_profiler.py` — cProfile hotspot analysis
- `evo_pollinator.py` — Cross-island strategy migration

### Plan Format
Plans live in `plan.yaml` with phases → tasks → must_haves (truths/artifacts/key_links), file_scope (owns/reads), wave assignments, and test dependency graphs. Task prompt files go in `tasks/task-{phase}.{task}.md`.

Key utilities: `scripts/plan_utils.py` (YAML manipulation, task state, token validation), `scripts/validate-plan.py` (schema validation), `scripts/phase_waves.py` (wave assignment).

## Prerequisites

Node.js >= 18, Python >= 3.8, git, jq, Claude Code CLI, OpenCode CLI. FastMCP (`pip install fastmcp`) for the MCP server. ANTHROPIC_API_KEY or Claude Code OAuth subscription for agent spawning.

## Key Conventions

- Agent signal types follow the pattern: `PHASE_ASSESSMENT_PASS`, `TESTS_WRITTEN`, `ASSESSMENT_PASS`, `IMPLEMENTATION_READY`, `VERIFICATION_PASS` (and corresponding `_FAIL` variants)
- Token secret files: `*-token.secret` (never committed)
- Session state directories: `.claude/gk-sessions/{phase_id}/` and `.claude/gk-sessions/task-{id}/`
- Planning state: `.planning/` (PROJECT.md, STATE.md, config.json, codebase analysis, phases)
- Hook compilation: `scripts/build-hooks.js` bundles `intel-index.js` with esbuild into `hooks/dist/`
