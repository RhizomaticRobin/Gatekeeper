#!/usr/bin/env bash
set -euo pipefail

# Gatekeeper Bootstrap Installer
# Checks prerequisites, builds MCP servers, installs the plugin to Claude Code.
#
# Usage:
#   git clone --recurse-submodules https://github.com/RhizomaticRobin/gatekeeper.git
#   cd gatekeeper
#   bash scripts/bootstrap.sh [--local]
#
# Options:
#   --local    Install to ./.claude/plugins/ (current project only)
#              Default: install to ~/.claude/plugins/ (global)

# Colors
RED='\033[38;2;220;20;60m'
GREEN='\033[32m'
YELLOW='\033[33m'
DIM='\033[2m'
BOLD='\033[1m'
RESET='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"
INSTALL_MODE="global"
ERRORS=()

if [[ "${1:-}" == "--local" ]]; then
  INSTALL_MODE="local"
fi

echo ""
echo -e "${RED} ██████╗  █████╗ ████████╗███████╗██╗  ██╗███████╗███████╗██████╗ ███████╗██████╗${RESET}"
echo -e "${RED}██╔════╝ ██╔══██╗╚══██╔══╝██╔════╝██║ ██╔╝██╔════╝██╔════╝██╔══██╗██╔════╝██╔══██╗${RESET}"
echo -e "${RED}██║  ███╗███████║   ██║   █████╗  █████╔╝ █████╗  █████╗  ██████╔╝█████╗  ██████╔╝${RESET}"
echo -e "${RED}██║   ██║██╔══██║   ██║   ██╔══╝  ██╔═██╗ ██╔══╝  ██╔══╝  ██╔═══╝ ██╔══╝  ██╔══██╗${RESET}"
echo -e "${RED}╚██████╔╝██║  ██║   ██║   ███████╗██║  ██╗███████╗███████╗██║     ███████╗██║  ██║${RESET}"
echo -e "${RED} ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝     ╚══════╝╚═╝  ╚═╝${RESET}"
echo ""
echo -e "  ${DIM}Bootstrap Installer${RESET}"
echo ""

# ─── Step 1: Check prerequisites ───────────────────────────────────────────────

echo -e "${BOLD}Checking prerequisites...${RESET}"
echo ""

check_cmd() {
  local cmd="$1"
  local label="$2"
  local min_version="${3:-}"
  local install_hint="${4:-}"

  if command -v "$cmd" &>/dev/null; then
    local version
    version=$("$cmd" --version 2>/dev/null | head -1 || "$cmd" version 2>/dev/null | head -1 || echo "unknown")
    echo -e "  ${GREEN}✓${RESET} ${label}: ${DIM}${version}${RESET}"
    return 0
  else
    echo -e "  ${RED}✗${RESET} ${label}: ${YELLOW}not found${RESET}"
    if [[ -n "$install_hint" ]]; then
      echo -e "    ${DIM}${install_hint}${RESET}"
    fi
    ERRORS+=("$label is required but not installed")
    return 1
  fi
}

check_cmd "node" "Node.js (>= 18)" "18" "Install: https://nodejs.org/ or 'nvm install 18'"
check_cmd "npm" "npm" "" ""
check_cmd "python3" "Python 3" "3.8" "Install: https://python.org/downloads/"
check_cmd "git" "git" "" "Install: https://git-scm.com/downloads"
check_cmd "jq" "jq" "" "Install: apt install jq / brew install jq"

# Claude Code — optional at bootstrap time (needed at runtime)
if command -v claude &>/dev/null; then
  CLAUDE_VERSION=$(claude --version 2>/dev/null | head -1 || echo "unknown")
  echo -e "  ${GREEN}✓${RESET} Claude Code: ${DIM}${CLAUDE_VERSION}${RESET}"
else
  echo -e "  ${YELLOW}!${RESET} Claude Code: ${YELLOW}not found${RESET}"
  echo -e "    ${DIM}Install: npm install -g @anthropic-ai/claude-code${RESET}"
  echo -e "    ${DIM}(Required at runtime, not for building)${RESET}"
fi

# OpenCode — optional at bootstrap time (needed at runtime)
if command -v opencode &>/dev/null; then
  OPENCODE_VERSION=$(opencode version 2>/dev/null | head -1 || echo "unknown")
  echo -e "  ${GREEN}✓${RESET} OpenCode: ${DIM}${OPENCODE_VERSION}${RESET}"
elif [[ -x "$HOME/.opencode/bin/opencode" ]]; then
  echo -e "  ${GREEN}✓${RESET} OpenCode: ${DIM}found at ~/.opencode/bin/opencode${RESET}"
else
  echo -e "  ${YELLOW}!${RESET} OpenCode: ${YELLOW}not found${RESET}"
  echo -e "    ${DIM}Install: curl -fsSL https://opencode.ai/install | bash${RESET}"
  echo -e "    ${DIM}(Required at runtime for agent dispatch)${RESET}"
fi

# Check Node.js version >= 18
if command -v node &>/dev/null; then
  NODE_MAJOR=$(node -e "console.log(process.versions.node.split('.')[0])")
  if [[ "$NODE_MAJOR" -lt 18 ]]; then
    echo -e "  ${RED}✗${RESET} Node.js version ${NODE_MAJOR} is too old (need >= 18)"
    ERRORS+=("Node.js >= 18 required, found ${NODE_MAJOR}")
  fi
fi

echo ""

if [[ ${#ERRORS[@]} -gt 0 ]]; then
  echo -e "${RED}Missing prerequisites:${RESET}"
  for err in "${ERRORS[@]}"; do
    echo -e "  ${RED}✗${RESET} $err"
  done
  echo ""
  echo "Install the missing dependencies and re-run this script."
  exit 1
fi

# ─── Step 2: Check submodule ───────────────────────────────────────────────────

echo -e "${BOLD}Checking submodules...${RESET}"
echo ""

cd "$PLUGIN_ROOT"

if [[ ! -f "Better-OpenCodeMCP/package.json" ]]; then
  echo -e "  ${DIM}Initializing submodules...${RESET}"
  git submodule update --init --recursive 2>&1 | while read -r line; do
    echo -e "    ${DIM}${line}${RESET}"
  done

  if [[ ! -f "Better-OpenCodeMCP/package.json" ]]; then
    echo -e "  ${RED}✗${RESET} Better-OpenCodeMCP submodule failed to initialize"
    echo -e "    ${DIM}Try: git submodule update --init --recursive${RESET}"
    exit 1
  fi
fi
echo -e "  ${GREEN}✓${RESET} Better-OpenCodeMCP submodule present"

# ─── Step 3: Build OpenCode MCP server ─────────────────────────────────────────

echo ""
echo -e "${BOLD}Building OpenCode MCP server...${RESET}"
echo ""

cd "$PLUGIN_ROOT/Better-OpenCodeMCP"

if [[ ! -d "node_modules" ]]; then
  echo -e "  ${DIM}Installing dependencies...${RESET}"
  npm install --production=false 2>&1 | tail -1
fi
echo -e "  ${GREEN}✓${RESET} Dependencies installed"

echo -e "  ${DIM}Building...${RESET}"
npm run build 2>&1 | tail -1

if [[ -f "dist/index.js" ]]; then
  echo -e "  ${GREEN}✓${RESET} Built: dist/index.js"
else
  echo -e "  ${RED}✗${RESET} Build failed — dist/index.js not found"
  exit 1
fi

# ─── Step 4: Build Verifier MCP server ─────────────────────────────────────────

cd "$PLUGIN_ROOT"
echo ""
echo -e "${BOLD}Building Verifier MCP server...${RESET}"
echo ""

cd "$PLUGIN_ROOT/verifier-mcp"

if [[ ! -d "node_modules" ]]; then
  echo -e "  ${DIM}Installing dependencies...${RESET}"
  npm install --production=false 2>&1 | tail -1
fi
echo -e "  ${GREEN}✓${RESET} Dependencies installed"

echo -e "  ${DIM}Building...${RESET}"
npm run build 2>&1 | tail -1

if [[ -f "dist/index.js" ]]; then
  echo -e "  ${GREEN}✓${RESET} Built: dist/index.js"
else
  echo -e "  ${RED}✗${RESET} Build failed — dist/index.js not found"
  exit 1
fi

# ─── Step 5: Build hook scripts ────────────────────────────────────────────────

cd "$PLUGIN_ROOT"
echo ""
echo -e "${BOLD}Building hook scripts...${RESET}"
echo ""

if [[ ! -d "node_modules" ]]; then
  echo -e "  ${DIM}Installing root dependencies...${RESET}"
  npm install 2>&1 | tail -1
fi

npm run build:hooks 2>&1 | tail -1

if [[ -f "hooks/dist/intel-index.js" ]]; then
  echo -e "  ${GREEN}✓${RESET} Built: hooks/dist/intel-index.js"
else
  echo -e "  ${YELLOW}!${RESET} hooks/dist/intel-index.js not found (non-critical)"
fi

# ─── Step 6: Make scripts executable ───────────────────────────────────────────

echo ""
echo -e "${BOLD}Making scripts executable...${RESET}"
echo ""

EXEC_COUNT=0
while IFS= read -r -d '' f; do
  chmod +x "$f"
  EXEC_COUNT=$((EXEC_COUNT + 1))
done < <(find "$PLUGIN_ROOT" -name "*.sh" -print0)

# Also hooks JS files
for f in "$PLUGIN_ROOT"/hooks/*.js "$PLUGIN_ROOT"/hooks/dist/*.js; do
  if [[ -f "$f" ]]; then
    chmod +x "$f"
    EXEC_COUNT=$((EXEC_COUNT + 1))
  fi
done

echo -e "  ${GREEN}✓${RESET} Made ${EXEC_COUNT} files executable"

# ─── Step 7: Install plugin ───────────────────────────────────────────────────

echo ""
echo -e "${BOLD}Installing plugin...${RESET}"
echo ""

if command -v claude &>/dev/null; then
  if [[ "$INSTALL_MODE" == "local" ]]; then
    echo -e "  ${DIM}Installing locally via plugin system...${RESET}"
    claude plugin marketplace add "$PLUGIN_ROOT" 2>&1 | while read -r line; do
      echo -e "    ${DIM}${line}${RESET}"
    done
    claude plugin install gatekeeper --scope local 2>&1 | while read -r line; do
      echo -e "    ${DIM}${line}${RESET}"
    done
    echo -e "  ${GREEN}✓${RESET} Installed locally to ./.claude/plugins/"
  else
    echo -e "  ${DIM}Installing globally via plugin system...${RESET}"
    claude plugin marketplace add "$PLUGIN_ROOT" 2>&1 | while read -r line; do
      echo -e "    ${DIM}${line}${RESET}"
    done
    claude plugin install gatekeeper --scope user 2>&1 | while read -r line; do
      echo -e "    ${DIM}${line}${RESET}"
    done
    echo -e "  ${GREEN}✓${RESET} Installed globally to ~/.claude/plugins/"
  fi
else
  # Fallback: use the legacy installer
  echo -e "  ${YELLOW}!${RESET} Claude Code CLI not found — using legacy installer"
  if [[ "$INSTALL_MODE" == "local" ]]; then
    node "$PLUGIN_ROOT/bin/install.js" --local
  else
    node "$PLUGIN_ROOT/bin/install.js" --global
  fi
fi

# ─── Step 8: Verify installation ──────────────────────────────────────────────

echo ""
echo -e "${BOLD}Verifying installation...${RESET}"
echo ""

VERIFY_PASS=true

check_file() {
  local path="$1"
  local label="$2"
  if [[ -f "$path" ]]; then
    echo -e "  ${GREEN}✓${RESET} ${label}"
  else
    echo -e "  ${RED}✗${RESET} ${label}: ${YELLOW}not found${RESET}"
    VERIFY_PASS=false
  fi
}

check_file "$PLUGIN_ROOT/Better-OpenCodeMCP/dist/index.js" "opencode-mcp server built"
check_file "$PLUGIN_ROOT/verifier-mcp/dist/index.js" "verifier-mcp server built"
check_file "$PLUGIN_ROOT/.claude-plugin/plugin.json" "plugin.json manifest"
check_file "$PLUGIN_ROOT/hooks/hooks.json" "hooks.json registration"
check_file "$PLUGIN_ROOT/agents/executor.md" "executor agent definition"
check_file "$PLUGIN_ROOT/agents/tester.md" "tester agent definition"
check_file "$PLUGIN_ROOT/agents/verifier.md" "verifier agent definition"
check_file "$PLUGIN_ROOT/templates/opencode.json" "opencode.json template"
check_file "$PLUGIN_ROOT/bin/opencode-mcp.sh" "opencode-mcp launcher"
check_file "$PLUGIN_ROOT/bin/verifier-mcp.sh" "verifier-mcp launcher"

echo ""

if [[ "$VERIFY_PASS" == "true" ]]; then
  echo -e "${GREEN}Installation complete!${RESET}"
  echo ""
  echo -e "  ${BOLD}Next steps:${RESET}"
  echo -e "  1. Restart Claude Code (or start a new session)"
  echo -e "  2. Run ${RED}/mcp${RESET} to verify MCP servers are loaded"
  echo -e "  3. Run ${RED}/gatekeeper:help${RESET} to see available commands"
  echo -e "  4. Run ${RED}/gatekeeper:quest${RESET} to plan your first project"
  echo ""
  if ! command -v claude &>/dev/null; then
    echo -e "  ${YELLOW}Reminder:${RESET} Install Claude Code before using the plugin:"
    echo -e "    ${DIM}npm install -g @anthropic-ai/claude-code${RESET}"
    echo ""
  fi
  if ! command -v opencode &>/dev/null && [[ ! -x "$HOME/.opencode/bin/opencode" ]]; then
    echo -e "  ${YELLOW}Reminder:${RESET} Install OpenCode before running /cross-team:"
    echo -e "    ${DIM}curl -fsSL https://opencode.ai/install | bash${RESET}"
    echo ""
  fi
else
  echo -e "${RED}Installation incomplete — some files are missing.${RESET}"
  echo "Check the errors above and re-run this script."
  exit 1
fi
