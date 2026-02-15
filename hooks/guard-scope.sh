#!/bin/bash

# Guard Scope Hook (PreToolUse: Read|Bash|Grep|Glob) — GSD-VGL
#
# Blocks agents from reading infrastructure files outside their working scope.
# Only active during VGL execution (verifier-loop.local.md exists).
#
# Restricted paths:
#   - *-token.secret              (completion tokens)
#   - *-prompt.local.md           (generated prompts)
#   - .claude/plugins/            (plugin cache)
#   - gsd-vgl/                    (plugin source, if present in project)
#   - verifier-mcp/               (MCP server source)
#   - agents/                     (agent definitions)
#   - hooks/                      (hook scripts)
#   - commands/                   (slash command definitions)
#
# NOT restricted:
#   - .claude/plan/ (task prompts and plan.yaml — agents need these)
#   - .planning/   (evolution data — executor needs this)
#   - Source code, tests, config files

INPUT=$(cat)

# Only guard during active VGL
if [[ ! -f ".claude/verifier-loop.local.md" ]]; then
  exit 0
fi

TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)

if [[ -z "$TOOL" ]]; then
  exit 0
fi

# --- Read tool: check file_path ---
if [[ "$TOOL" == "Read" ]]; then
  FILEPATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
  if [[ -z "$FILEPATH" ]]; then
    exit 0
  fi

  case "$FILEPATH" in
    *-token.secret|*token.secret*)
      echo "BLOCKED: That file is outside your working scope." >&2
      exit 2
      ;;
    *-prompt.local.md|*prompt.local.md*)
      echo "BLOCKED: That file is outside your working scope." >&2
      exit 2
      ;;
    */.claude/plugins/*|*/.claude/plugins)
      echo "BLOCKED: That directory is outside your working scope." >&2
      exit 2
      ;;
    */gsd-vgl/*|*/gsd-vgl)
      echo "BLOCKED: That directory is outside your working scope." >&2
      exit 2
      ;;
    */verifier-mcp/*|*/verifier-mcp)
      echo "BLOCKED: That directory is outside your working scope." >&2
      exit 2
      ;;
    */agents/*.md)
      echo "BLOCKED: That file is outside your working scope." >&2
      exit 2
      ;;
    */hooks/*|*/hooks)
      echo "BLOCKED: That directory is outside your working scope." >&2
      exit 2
      ;;
    */commands/*|*/commands)
      echo "BLOCKED: That directory is outside your working scope." >&2
      exit 2
      ;;
    */scripts/generate-*|*/scripts/fetch-*|*/scripts/setup-*)
      echo "BLOCKED: That file is outside your working scope." >&2
      exit 2
      ;;
    */.claude/vgl-sessions/*|*vgl-sessions/*.secret|*vgl-sessions/*.local.md)
      echo "BLOCKED: That file is outside your working scope." >&2
      exit 2
      ;;
  esac
  exit 0
fi

# --- Bash tool: check command for restricted file access ---
if [[ "$TOOL" == "Bash" ]]; then
  CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
  if [[ -z "$CMD" ]]; then
    exit 0
  fi

  # Lowercase the command for case-insensitive matching
  CMD_LOWER="${CMD,,}"

  # Check if command uses a file-reading utility
  HAS_READ_CMD=false
  case "$CMD_LOWER" in
    *cat\ *|*head\ *|*tail\ *|*less\ *|*more\ *|*bat\ *|*hexdump\ *|*xxd\ *|*strings\ *|*base64\ *)
      HAS_READ_CMD=true ;;
    *python*open\(*|*node*readfile*|*ruby*file.read*)
      HAS_READ_CMD=true ;;
  esac

  if [[ "$HAS_READ_CMD" == "true" ]]; then
    # Check if command references restricted paths
    case "$CMD" in
      *token.secret*|*prompt.local.md*)
        echo "BLOCKED: That command accesses files outside your working scope." >&2
        exit 2
        ;;
      *.claude/plugins*|*gsd-vgl/*|*verifier-mcp/*)
        echo "BLOCKED: That command accesses files outside your working scope." >&2
        exit 2
        ;;
      *agents/*.md*|*/hooks/*|*/commands/*)
        echo "BLOCKED: That command accesses files outside your working scope." >&2
        exit 2
        ;;
      *scripts/generate-*|*scripts/fetch-*|*scripts/setup-*)
        echo "BLOCKED: That command accesses files outside your working scope." >&2
        exit 2
        ;;
      *vgl-sessions/*)
        echo "BLOCKED: That command accesses files outside your working scope." >&2
        exit 2
        ;;
    esac
  fi
  exit 0
fi

# --- Grep tool: check path ---
if [[ "$TOOL" == "Grep" ]]; then
  GREPPATH=$(echo "$INPUT" | jq -r '.tool_input.path // empty' 2>/dev/null)
  if [[ -z "$GREPPATH" ]]; then
    exit 0
  fi

  case "$GREPPATH" in
    */.claude/plugins/*|*/.claude/plugins|*/gsd-vgl/*|*/gsd-vgl|*/verifier-mcp/*|*/verifier-mcp|*/agents/*|*/hooks/*|*/hooks|*/commands/*|*/commands)
      echo "BLOCKED: That path is outside your working scope." >&2
      exit 2
      ;;
    */.claude/vgl-sessions/*|*/.claude/vgl-sessions|*vgl-sessions/*)
      echo "BLOCKED: That path is outside your working scope." >&2
      exit 2
      ;;
    *token.secret*|*prompt.local.md*)
      echo "BLOCKED: That path is outside your working scope." >&2
      exit 2
      ;;
  esac
  exit 0
fi

# --- Glob tool: check path ---
if [[ "$TOOL" == "Glob" ]]; then
  GLOBPATH=$(echo "$INPUT" | jq -r '.tool_input.path // empty' 2>/dev/null)
  if [[ -z "$GLOBPATH" ]]; then
    exit 0
  fi

  case "$GLOBPATH" in
    */.claude/plugins/*|*/.claude/plugins|*/gsd-vgl/*|*/gsd-vgl|*/verifier-mcp/*|*/verifier-mcp|*/agents/*|*/hooks/*|*/hooks|*/commands/*|*/commands)
      echo "BLOCKED: That path is outside your working scope." >&2
      exit 2
      ;;
    */.claude/vgl-sessions/*|*/.claude/vgl-sessions|*vgl-sessions/*)
      echo "BLOCKED: That path is outside your working scope." >&2
      exit 2
      ;;
  esac
  exit 0
fi

exit 0
