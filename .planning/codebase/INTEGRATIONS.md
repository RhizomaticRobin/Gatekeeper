# External Integrations

## Claude Code Plugin System

| Integration Point | Mechanism | Files |
|-------------------|-----------|-------|
| Commands (skills) | `/gsd-vgl:command` → `commands/*.md` | 14 command files |
| Agents | `Task(subagent_type='agent-name')` | 9 agent files |
| Hooks | `hooks.json` event registration | stop-hook.sh, guard-skills.sh, post-cross.sh, intel-index.js |
| MCP servers | `plugin.json` → `mcpServers` | opencode-mcp via bin/opencode-mcp.sh |
| Plugin root | `${CLAUDE_PLUGIN_ROOT}` variable | Used in hooks.json, plugin.json |

## OpenCode MCP Server

**Interface:** 3 tools exposed to Claude Code

| Tool | Purpose | Used By |
|------|---------|---------|
| `launch_opencode(task, sessionId?, model?)` | Spawn or continue gsd-builder agent | Executor |
| `wait_for_completion(taskIds?)` | Wait for agents to finish (10min timeout) | Executor |
| `opencode_sessions(status?)` | List active/completed sessions | Executor |

**Agent profile:** gsd-builder (hardcoded server-side)
- No web access, temp 1.0, no step limit
- Bash (ask), Edit/Write (allow)

**Question handling:** Agent sends `input_required` status → executor answers via `launch_opencode(sessionId=..., task="answer")`

## Git

- Checkpoint commits via Ralph autopilot: `checkpoint(task-{id}): {summary}`
- Submodule: Better-OpenCodeMCP tracked via `.gitmodules`
- Not yet: automated commits per task completion

## Playwright (Verifier)

- Visual verification of qualitative criteria
- Navigate to `dev_server_url` from plan.yaml metadata
- Take screenshots, interact with UI, check console
- Verifier decides pass/fail based on visual assessment

## File System State (.claude/ directory)

All VGL state managed via files — no database, no external service:
- `plan.yaml` — master plan
- `task-{id}.md` — task specs
- `verifier-loop.local.md` — VGL iteration state
- `verifier-token.secret` — cryptographic token (chmod 600)
- `verifier-prompt.local.md` — immutable verifier prompt
- `vgl-team-active` — team mode flag
