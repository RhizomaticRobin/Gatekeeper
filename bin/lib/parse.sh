#!/bin/bash
# GSD-VGL Ralph - Plan.yaml Parsing
# Adapted from GSD's STATE.md/ROADMAP.md parsing to use plan.yaml
#
# Functions: parse_next_task, find_task_prompt, get_task_name,
#            get_all_phases, count_tasks
#
# Usage:
#   source bin/lib/parse.sh
#   parse_next_task           # Returns task ID (e.g., "1.1") or "COMPLETE"
#   find_task_prompt "1.1"    # Returns path to task-1.1.md
#   get_task_name "1.1"       # Returns task name

# Configuration
PLAN_FILE="${PLAN_FILE:-.claude/plan/plan.yaml}"
STATE_FILE="${STATE_FILE:-.planning/STATE.md}"
ROADMAP_FILE="${ROADMAP_FILE:-.planning/ROADMAP.md}"

# Color codes for error messages
PARSE_RED='\e[31m'
PARSE_YELLOW='\e[33m'
PARSE_RESET='\e[0m'

# Resolve scripts directory relative to this file
PARSE_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$PARSE_SCRIPT_DIR/../.." && pwd)"

# parse_next_task - Find next unblocked task from plan.yaml
# Returns: Task ID (e.g., "1.1") on success, "COMPLETE" if all done
# Return code: 0 on success, 1 on failure
parse_next_task() {
    if [[ ! -f "$PLAN_FILE" ]]; then
        echo -e "${PARSE_RED}Error: PLAN_FILE not found: $PLAN_FILE${PARSE_RESET}" >&2
        return 1
    fi

    # Use next-task.py to find the next unblocked task
    local next_json
    next_json=$(python3 "${PLUGIN_ROOT}/scripts/next-task.py" "$PLAN_FILE" 2>/dev/null)

    if [[ "$next_json" == "null" ]] || [[ -z "$next_json" ]]; then
        echo "COMPLETE"
        return 0
    fi

    # Extract task ID from JSON
    local task_id
    task_id=$(echo "$next_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)

    if [[ -z "$task_id" ]]; then
        echo "COMPLETE"
        return 0
    fi

    echo "$task_id"
    return 0
}

# find_task_prompt - Find the path to a task prompt file
# Args: task_id (e.g., "1.1")
# Returns: Full path to task-{id}.md file
# Return code: 0 on success, 1 if not found
find_task_prompt() {
    local task_id="$1"

    if [[ -z "$task_id" ]]; then
        echo -e "${PARSE_RED}Error: find_task_prompt requires task_id${PARSE_RESET}" >&2
        return 1
    fi

    # Get prompt_file from plan.yaml
    local prompt_file
    prompt_file=$(python3 -c "
import sys
sys.path.insert(0, '${PLUGIN_ROOT}/scripts')
from plan_utils import load_plan, find_task
plan = load_plan('$PLAN_FILE')
_, task = find_task(plan, '$task_id')
if task:
    print(task.get('prompt_file', ''))
" 2>/dev/null)

    if [[ -z "$prompt_file" ]]; then
        echo -e "${PARSE_RED}Error: No prompt_file for task $task_id${PARSE_RESET}" >&2
        return 1
    fi

    local full_path=".claude/plan/${prompt_file}"
    if [[ ! -f "$full_path" ]]; then
        echo -e "${PARSE_RED}Error: Task prompt not found: $full_path${PARSE_RESET}" >&2
        return 1
    fi

    echo "$full_path"
    return 0
}

# find_plan_file - Alias for backward compat with ralph.sh
# In gsd-vgl, this maps to find_task_prompt
find_plan_file() {
    find_task_prompt "$1"
}

# get_task_name - Get task name from plan.yaml
# Args: task_id (e.g., "1.1")
# Returns: Task name string
get_task_name() {
    local task_id="$1"

    if [[ -z "$task_id" ]]; then
        echo "Unknown task"
        return 0
    fi

    local name
    name=$(python3 -c "
import sys
sys.path.insert(0, '${PLUGIN_ROOT}/scripts')
from plan_utils import load_plan, find_task
plan = load_plan('$PLAN_FILE')
_, task = find_task(plan, '$task_id')
if task:
    print(task.get('name', 'Task $task_id'))
else:
    print('Task $task_id')
" 2>/dev/null)

    echo "${name:-Task $task_id}"
    return 0
}

# get_plan_name - Alias for backward compat
get_plan_name() {
    get_task_name "$1"
}

# get_next_plan_after - Find the next task after current
# Args: current_task_id (e.g., "1.1")
# Returns: Next task ID or "COMPLETE"
get_next_plan_after() {
    local current_task_id="$1"

    if [[ -z "$current_task_id" ]]; then
        echo "COMPLETE"
        return 0
    fi

    # Mark current as complete, then find next
    # (But don't actually modify plan - just simulate)
    local next_json
    next_json=$(python3 -c "
import sys
sys.path.insert(0, '${PLUGIN_ROOT}/scripts')
from plan_utils import load_plan, get_all_task_ids, find_task, get_next_task
plan = load_plan('$PLAN_FILE')
# Find the task after current by looking at all tasks
all_tasks = []
for phase in plan.get('phases', []):
    for task in phase.get('tasks', []):
        all_tasks.append(task)
found_current = False
for task in all_tasks:
    if str(task['id']) == '$current_task_id':
        found_current = True
        continue
    if found_current and task.get('status') == 'pending':
        print(str(task['id']))
        sys.exit(0)
print('COMPLETE')
" 2>/dev/null)

    echo "${next_json:-COMPLETE}"
    return 0
}

# get_all_phases - Return list of all phase IDs from plan.yaml
get_all_phases() {
    if [[ ! -f "$PLAN_FILE" ]]; then
        return 1
    fi

    python3 -c "
import sys
sys.path.insert(0, '${PLUGIN_ROOT}/scripts')
from plan_utils import load_plan
plan = load_plan('$PLAN_FILE')
phases = [str(p['id']) for p in plan.get('phases', [])]
print(' '.join(phases))
" 2>/dev/null
    return 0
}

# count_tasks - Count total and completed tasks
count_tasks() {
    if [[ ! -f "$PLAN_FILE" ]]; then
        echo "0 0"
        return 0
    fi

    python3 -c "
import sys
sys.path.insert(0, '${PLUGIN_ROOT}/scripts')
from plan_utils import load_plan
plan = load_plan('$PLAN_FILE')
total = 0
completed = 0
for phase in plan.get('phases', []):
    for task in phase.get('tasks', []):
        total += 1
        if task.get('status') == 'completed':
            completed += 1
print(f'{total} {completed}')
" 2>/dev/null
    return 0
}

# phase_has_plans - Check if a phase has tasks (compat shim)
phase_has_plans() {
    return 0
}

# get_phase_name - Get phase name (compat shim)
get_phase_name() {
    local phase_num="$1"
    if [[ ! -f "$PLAN_FILE" ]]; then
        echo "Phase $phase_num"
        return 0
    fi

    python3 -c "
import sys
sys.path.insert(0, '${PLUGIN_ROOT}/scripts')
from plan_utils import load_plan
plan = load_plan('$PLAN_FILE')
for phase in plan.get('phases', []):
    if str(phase['id']) == '$phase_num':
        print(phase.get('name', 'Phase $phase_num'))
        sys.exit(0)
print('Phase $phase_num')
" 2>/dev/null
    return 0
}

# get_unplanned_phases - Not applicable in gsd-vgl (compat shim)
get_unplanned_phases() {
    echo ""
    return 0
}

# count_phase_plans - Not applicable in gsd-vgl (compat shim)
count_phase_plans() {
    echo "0"
    return 0
}
