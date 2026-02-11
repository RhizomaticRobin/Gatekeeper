# Technology Stack

## Languages

| Language | Version | Usage |
|----------|---------|-------|
| Bash | POSIX sh, `set -euo pipefail` | Core scripting — VGL loop, hooks, task transitions, orchestration |
| Python 3 | 3.6+ (PyYAML required) | Plan utilities, validation, task queries, topological sort |
| JavaScript/Node.js | 16.7.0+ | Installer, hook bundling, codebase intelligence indexer |
| TypeScript | (submodule) | Better-OpenCodeMCP MCP server |
| Markdown | CommonMark + YAML frontmatter | Agent prompts, command definitions, documentation |

## Frameworks & Libraries

### npm (package.json)

| Package | Version | Type | Purpose |
|---------|---------|------|---------|
| `command-exists` | ^1.2.9 | Runtime | Check if CLI tools exist on PATH |
| `esbuild` | ^0.24.0 | Dev | Bundle hooks (intel-index.js + sql.js) |
| `sql.js` | ^1.12.0 | Dev (bundled) | SQLite in JS for dependency graph indexing |

### Python (implicit)

| Package | Required | Purpose |
|---------|----------|---------|
| `PyYAML` | Yes | YAML parsing/writing for plan.yaml |

### External Tools (required at runtime)

| Tool | Used By | Purpose |
|------|---------|---------|
| `jq` | stop-hook.sh, scripts | JSON parsing |
| `base64` | fetch-completion-token.sh | Test command encoding |
| `sha256sum` | fetch-completion-token.sh | Integrity verification |
| `git` | Autopilot, checkpoint commits | Version control |
| `claude` | installer, MCP registration | Claude Code CLI |

## Build Tools

- `npm run build:hooks` — Bundles intel-index.js with sql.js via esbuild
- Better-OpenCodeMCP: `npm run build` (TypeScript → JavaScript via tsc)

## MCP Server

Declared in `plugin.json`, launched by `bin/opencode-mcp.sh`:
- Auto-clones Better-OpenCodeMCP submodule if missing
- Auto-installs deps and builds on first run
- Hardcoded agent: `gsd-builder` (temp 1.0, no web, no step limit)
