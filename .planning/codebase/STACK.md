# Stack

## Languages
- **Bash** — Primary scripting language for hooks, Gatekeeper scripts, autopilot (ralph.sh), and bin/ utilities. ~6,000 LOC across scripts/, hooks/, bin/.
- **Python 3** — Plan utilities, validation, evolutionary intelligence, history, learnings. ~3,500 LOC in scripts/*.py. Requires PyYAML.
- **JavaScript/Node.js** (>=16.7.0) — Installer (bin/install.js), hook bundler (build-hooks.js), intel-index.js, progress-watcher, terminal-launcher. ~2,500 LOC.
- **Markdown** — Agent definitions (9 .md files with YAML frontmatter), slash commands (15 .md files), workflow docs, reference docs, templates. These are executable prompts, not documentation.

## Frameworks & Major Dependencies
- **Claude Code Plugin System** — Plugin manifest at `.claude-plugin/plugin.json`. Hooks, commands, agents, MCP servers declared via plugin JSON.
- **PyYAML** — Required for plan.yaml parsing/writing in Python scripts.
- **sql.js** (devDep) — SQLite WASM for intel-index.js hook (codebase intelligence indexer).
- **esbuild** (devDep) — Bundles intel-index.js with sql.js WASM inlined.

## Test Frameworks
- **pytest** — Python tests in `tests/python/`. Config in `pytest.ini`.
- **bats-core** (v1.13) — Bash tests in `tests/bash/` and `tests/e2e/`. Uses bats-assert, bats-support, bats-file.
- **vitest** (v4.0) — Node.js tests in `tests/node/`. Config in `vitest.config.js`.

## Runtime Requirements
- **Claude Code CLI** (`claude` command) — Required for autopilot (ralph.sh) and agent spawning.
- **Node.js** >= 16.7.0 — MCP server, installer, hook bundling.
- **Python 3** — Plan utilities, validation, evolutionary intelligence.
- **jq** — JSON parsing in shell scripts (hooks, setup scripts).
- **openssl** — 128-bit token generation (`openssl rand -hex 16`).
- **flock** — File locking for concurrent plan.yaml access.
- **Playwright** — Visual verification in the verifier agent (browser tools).
- **Git** — Checkpoint commits in autopilot mode.

## Build Configuration
- `npm run build:hooks` — esbuild bundles intel-index.js to hooks/dist/.
- `npm run prepublishOnly` — Runs build:hooks before npm publish.

## Distribution
- **npm package** (`gatekeeper` v1.0.0) — `npx gatekeeper` for legacy install.
- **Claude Code Marketplace** — `plugin marketplace add RhizomaticRobin/gatekeeper`.
