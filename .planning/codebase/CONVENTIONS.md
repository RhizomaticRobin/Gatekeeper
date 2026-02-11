# Code Conventions

## Bash Scripts

**Header pattern:**
```bash
#!/bin/bash
set -euo pipefail
```

**Variables:** `UPPER_SNAKE_CASE` for config (`PLAN_FILE`, `PLUGIN_ROOT`), lowercase for locals
**Always quote:** `"$VAR"` not `$VAR`
**Argument validation:** `PLUGIN_ROOT="${1:?Usage: script.sh <plugin_root>}"`
**Errors to stderr:** `echo "Error: ..." >&2`
**JSON processing:** `jq` (not grep/sed for JSON)
**YAML frontmatter:** `sed -n '/^---$/,/^---$/{ /^---$/d; p; }'`

## Python Scripts

**Style:** Standard library only (except PyYAML), snake_case functions, docstrings
**CLI pattern:** Docstring with usage/exit codes, errors to stderr, results to stdout
**Optional imports:** `try: import yaml; except ImportError: yaml = None`
**Error handling:** `RuntimeError` with clear instructions

## JavaScript/Node.js

**Style:** `const` declarations, camelCase, semicolons, `require()` imports
**Error handling:** try/catch with `process.exit(1)` on failure
**Colors:** ANSI escape codes stored as constants (`crimson`, `green`, `yellow`)

## Markdown (Agents/Commands)

**Frontmatter (agents):**
```yaml
---
name: agent-name
description: One-sentence role
model: opus
tools: Read, Write, Bash, ...
disallowedTools: WebFetch, WebSearch, ...
---
```

**Frontmatter (commands):**
```yaml
---
description: What the command does
allowed-tools: ["Bash(...)", "Read", "Task"]
---
```

## Cross-Language Patterns

- **Fail fast** — All languages check prerequisites before proceeding
- **Info → stdout, errors → stderr** — Consistent across bash/python/node
- **Debug logging** — Optional, to `/tmp/gsd-vgl-*.debug.log`
- **Path handling** — `${CLAUDE_PLUGIN_ROOT}` in hooks/configs, `$(dirname "$0")` in scripts
