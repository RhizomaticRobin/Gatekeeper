#!/bin/bash

# Guard Scope Hook (PreToolUse: Read|Bash|Grep|Glob) — Gatekeeper
#
# Blocks agents from reading infrastructure files outside their working scope.
# Only active during Gatekeeper execution (verifier-loop.local.md exists).
#
# Restricted paths:
#   - *-token.secret              (completion tokens)
#   - *-prompt.local.md           (generated prompts)
#   - .claude/plugins/            (plugin cache)
#   - gatekeeper/                    (plugin source, if present in project)
#   - gatekeeper-evolve-mcp/               (MCP server source)
#   - agents/                     (agent definitions)
#   - hooks/                      (hook scripts)
#   - commands/                   (slash command definitions)
#
# NOT restricted:
#   - .claude/plan/ (task prompts and plan.yaml — agents need these)
#   - .planning/   (evolution data — executor needs this)
#   - Source code, tests, config files

INPUT=$(cat)

# Only guard during active Gatekeeper loop
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
    */gatekeeper/*|*/gatekeeper)
      echo "BLOCKED: That directory is outside your working scope." >&2
      exit 2
      ;;
    */gatekeeper-evolve-mcp/*|*/gatekeeper-evolve-mcp)
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
    */.claude/gk-sessions/*|*gk-sessions/*.secret|*gk-sessions/*.local.md)
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

  # Strip piped utility usage (encoding/truncation in pipes, not file reading)
  # e.g. "openssl rand | head -c 32", "echo $x | base64 -w0", "echo $x | sha256sum"
  CMD_READ_CHECK=$(echo "$CMD_LOWER" | sed -E \
    -e 's/\|[[:space:]]*(head|tail)[[:space:]]+-[[:alnum:]]+[[:space:]]+[0-9]+//g' \
    -e 's/\|[[:space:]]*(head|tail)[[:space:]]+-[0-9]+//g' \
    -e 's/\|[[:space:]]*(head|tail)[[:space:]]+[0-9]+//g' \
    -e 's/\|[[:space:]]*(base64|sha256sum|sha512sum|md5sum|wc|cut|tr|sort|uniq|grep|sed|awk)[[:space:]][^|;&)]*//g' \
    -e 's/\|[[:space:]]*(base64|sha256sum|sha512sum|md5sum|wc|cut|tr|sort|uniq|grep|sed|awk)[[:space:]]*$//g')

  # Check if command uses a file-reading utility
  HAS_READ_CMD=false
  case "$CMD_READ_CHECK" in
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
      *.claude/plugins*|*gatekeeper/*|*gatekeeper-evolve-mcp/*)
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
      *gk-sessions/*)
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
    */.claude/plugins/*|*/.claude/plugins|*/gatekeeper/*|*/gatekeeper|*/gatekeeper-evolve-mcp/*|*/gatekeeper-evolve-mcp|*/agents/*|*/hooks/*|*/hooks|*/commands/*|*/commands)
      echo "BLOCKED: That path is outside your working scope." >&2
      exit 2
      ;;
    */.claude/gk-sessions/*|*/.claude/gk-sessions|*gk-sessions/*)
      echo "BLOCKED: That path is outside your working scope." >&2
      exit 2
      ;;
    *token.secret*|*prompt.local.md*)
      echo "BLOCKED: That path is outside your working scope." >&2
      exit 2
      ;;
    */scripts/generate-*|*/scripts/fetch-*|*/scripts/setup-*)
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
    */.claude/plugins/*|*/.claude/plugins|*/gatekeeper/*|*/gatekeeper|*/gatekeeper-evolve-mcp/*|*/gatekeeper-evolve-mcp|*/agents/*|*/hooks/*|*/hooks|*/commands/*|*/commands)
      echo "BLOCKED: That path is outside your working scope." >&2
      exit 2
      ;;
    */.claude/gk-sessions/*|*/.claude/gk-sessions|*gk-sessions/*)
      echo "BLOCKED: That path is outside your working scope." >&2
      exit 2
      ;;
    *token.secret*|*prompt.local.md*)
      echo "BLOCKED: That path is outside your working scope." >&2
      exit 2
      ;;
    */scripts/generate-*|*/scripts/fetch-*|*/scripts/setup-*)
      echo "BLOCKED: That path is outside your working scope." >&2
      exit 2
      ;;
  esac
  exit 0
fi

exit 0
