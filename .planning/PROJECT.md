# Project: Gatekeeper

## Vision
Evolve Gatekeeper from a structured TDD/Gatekeeper plugin into a self-improving, autonomously-learning development system. Gatekeeper retains the cryptographic verification core but adds adaptive orchestration, cross-project learning, and end-to-end autonomy — reducing human intervention from "guide every task" to "describe what you want."

## Primary User
Software developers using Claude Code for complex, multi-task projects.

## Problem Statement
Current Gatekeeper orchestrates well but doesn't learn. Every project starts from zero — same wave sizes, same retry logic, same agent configurations. Failures repeat across runs. Orchestration is rigid (fixed waves, static dispatch). Human intervention is still required for decisions the system should be able to make itself.

## Success Criteria
- System accumulates learnings across projects and applies them to future runs
- Orchestration adapts dynamically (wave sizing, retry strategy, agent routing) based on task characteristics
- A project can go from `/quest` to fully verified completion with minimal human input
- Existing Gatekeeper, TDD, and verification guarantees remain intact (no regression)
- Test coverage for core scripts, hooks, and plan utilities

## Technical Stack
- **Languages:** JavaScript/Node.js (installer, hooks), Bash (scripts, hooks), Python (plan utilities), Markdown (agents, commands, prompts)
- **Plugin System:** Claude Code plugin (`.claude-plugin/plugin.json`, marketplace distribution)
- **MCP Server:** Better-OpenCodeMCP (TypeScript/Node.js submodule, hardcoded gk-builder agent)
- **Agent Models:** Opus for all agents (quality profile)

## Integrations
- Claude Code CLI (`claude` command)
- opencode MCP server (launch_opencode, wait_for_completion, opencode_sessions)
- Playwright (visual verification in verifier agent)
- Git (checkpoint commits, autopilot)

## Deployment
- npm package (`npx gatekeeper`)
- Claude Code marketplace (`/plugin marketplace add RhizomaticRobin/gatekeeper`)
