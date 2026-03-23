#!/usr/bin/env bash
# guard-write-scope.sh — blocks Write/Edit outside task's file_scope.owns
#
# PreToolUse hook for Write and Edit tools during team mode execution.
# Reads the current task's scope from .claude/gk-sessions/task-{id}/scope.json
# and blocks writes to files outside the task's file_scope.owns.

set -euo pipefail

PLUGIN_ROOT="$(dirname "$(dirname "$(realpath "$0")")")"
source "${PLUGIN_ROOT}/scripts/gk_log.sh"
source "${PLUGIN_ROOT}/bin/python3-resolve.sh"

HOOK_INPUT=$(cat)

TOOL_NAME=$(echo "$HOOK_INPUT" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null) || exit 0

# Only guard Write and Edit
[[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" ]] && exit 0

# Extract target file path
TARGET=$("$PYTHON" -c "
import sys, json
data = json.load(sys.stdin)
inp = data.get('tool_input', {})
print(inp.get('file_path', inp.get('path', '')))
" <<< "$HOOK_INPUT" 2>/dev/null) || exit 0

[[ -z "$TARGET" ]] && exit 0

# Skip if not in team mode
[[ ! -f ".claude/gk-team-active" ]] && exit 0

# Get active task ID
CURRENT_TASK=""
if [[ -f ".claude/gk-current-task" ]]; then
    CURRENT_TASK=$(cat .claude/gk-current-task 2>/dev/null)
fi
[[ -z "$CURRENT_TASK" ]] && exit 0

SCOPE_FILE=".claude/gk-sessions/task-${CURRENT_TASK}/scope.json"
[[ ! -f "$SCOPE_FILE" ]] && exit 0

# Check if target path is within any owned path
ALLOWED=$("$PYTHON" -c "
import json, sys, os

scope = json.load(open('$SCOPE_FILE'))
target = os.path.abspath('$TARGET')
project_root = os.getcwd()

# Normalize target to relative path
if target.startswith(project_root):
    target_rel = os.path.relpath(target, project_root)
else:
    target_rel = target

for owned in scope.get('owns', []):
    owned_norm = owned.rstrip('/')
    target_norm = target_rel.rstrip('/')
    # Exact match
    if target_norm == owned_norm:
        print('yes')
        sys.exit(0)
    # Target is inside owned directory
    if target_norm.startswith(owned_norm + '/'):
        print('yes')
        sys.exit(0)
    # Owned is a directory prefix
    if owned.endswith('/') and target_norm.startswith(owned_norm):
        print('yes')
        sys.exit(0)

print('no')
" 2>/dev/null) || exit 0

if [[ "$ALLOWED" == "no" ]]; then
    gk_warn "SCOPE VIOLATION: Write to $TARGET blocked — outside file_scope.owns for task $CURRENT_TASK"
    echo '{"error": "Write blocked: '"$TARGET"' is outside file_scope.owns for task '"$CURRENT_TASK"'. Only files listed in this task'\''s owns scope can be modified."}'
    exit 2
fi

exit 0
