# Integrations

## Claude Code CLI
- **Usage:** `claude` command invoked by `bin/ralph.sh` (autopilot) for spawning fresh Claude Code instances per task.
- **Plugin system:** `.claude-plugin/plugin.json` registers commands, agents, hooks, MCP servers with Claude Code.
- **Task() API:** Executor agents spawn sub-agents (verifier, integration-checker) via `Task(subagent_type=..., model=..., prompt=...)`.
- **Hook API:** Hooks receive JSON on stdin with `transcript_path`, `tool_input`, etc. Return JSON with `decision`, `reason`, `systemMessage`.

## Opencode MCP Server (Better-OpenCodeMCP)
- **Source:** Git submodule at `Better-OpenCodeMCP/`, GitHub: `RhizomaticRobin/Better-OpenCodeMCP`.
- **Launch:** `bin/opencode-mcp.sh` auto-clones, installs, builds on first run. Declared in plugin.json as `opencode-mcp`.
- **Tools exposed:** `launch_opencode(task, sessionId?)`, `wait_for_completion()`, `opencode_sessions`.
- **Agent profile:** All spawned agents use `gsd-builder` profile (hardcoded server-side). Config deployed from `templates/opencode.json`.
- **Model:** `zai-coding-plan/glm-4.7` for gsd-builder agents.

## Playwright (Visual Verification)
- **Usage:** Verifier agent uses Playwright browser tools for qualitative verification.
- **Tools:** `browser_navigate`, `browser_snapshot`, `browser_take_screenshot`, `browser_click`, `browser_type`, `browser_fill_form`, `browser_console_messages`.
- **Integration:** Referenced in `generate-verifier-prompt.sh` output. Verifier navigates to `dev_server_url` + `playwright_url` from task config.

## Git
- **Checkpoint commits:** `bin/lib/checkpoint.sh` creates `checkpoint(task-{id}): {summary}` commits during autopilot.
- **Submodule:** `Better-OpenCodeMCP` tracked via `.gitmodules`.

## File System State
- **Plan lock:** `plan.yaml.lock` — flock for mutual exclusion between Python (`fcntl.flock`) and Bash (`flock -x`).
- **Evolution DB:** `.planning/evolution/{task_id}/approaches.jsonl` + `metadata.json` — per-task population.
- **Run history:** `.planning/history/runs.jsonl` — JSONL append-only log.
- **Learnings:** `.planning/learnings.jsonl` — Extracted patterns from verifier feedback.

## Environment Variables
| Variable | Purpose | Set By |
|----------|---------|--------|
| `CLAUDE_PLUGIN_ROOT` | Plugin installation directory | Claude Code runtime |
| `GATEKEEPER_PLAN_LOCKED` | Skip Python flock when parent Bash holds lock | `transition-task.sh` |
| `PROJECT_DIR` | Override project directory for onboarding | User/script |
| `LOG_FILE` | Ralph log file path (default: `.planning/ralph.log`) | User/ralph.sh |
| `PAUSE_FILE` | Pause marker for ralph (default: `.planning/.pause`) | User/ralph.sh |

## No External API Calls
The plugin itself makes zero network requests at runtime. All intelligence comes from Claude models via the Claude Code runtime. The only network activity is:
- Git clone of Better-OpenCodeMCP submodule (first run only)
- npm install for MCP server dependencies (first run only)
