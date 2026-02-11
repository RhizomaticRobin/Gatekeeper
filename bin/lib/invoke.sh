#!/bin/bash
# GSD-VGL Ralph - Claude CLI Invocation
# Adapted from GSD to use /cross-team command instead of reading PLAN.md files
#
# Functions: invoke_claude, parse_claude_output, check_iteration_duration,
#            handle_iteration_failure, handle_claude_crash
#
# Usage:
#   source bin/lib/invoke.sh
#   result=$(invoke_claude "1.1")
#   exit_code=$?

# Source parse.sh for task functions
INVOKE_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${INVOKE_SCRIPT_DIR}/parse.sh"

# Color codes (consistent with display.sh)
if [[ -n "${NO_COLOR:-}" ]]; then
    INVOKE_RED=''
    INVOKE_GREEN=''
    INVOKE_YELLOW=''
    INVOKE_BOLD=''
    INVOKE_RESET=''
else
    INVOKE_RED='\e[31m'
    INVOKE_GREEN='\e[32m'
    INVOKE_YELLOW='\e[33m'
    INVOKE_BOLD='\e[1m'
    INVOKE_RESET='\e[0m'
fi

# Duration alert threshold (30 minutes in seconds)
DURATION_ALERT_THRESHOLD=1800

# invoke_claude - Invoke Claude Code CLI to execute a task via /cross-team
# Args: task_id (e.g., "1.1")
# Returns: 0 on success, 1 on failure
# Output: Claude's output file path (caller should parse)
invoke_claude() {
    local task_id="$1"

    if [[ -z "$task_id" ]]; then
        echo -e "${INVOKE_RED}Error: invoke_claude requires task_id${INVOKE_RESET}" >&2
        return 1
    fi

    # Get task name for logging
    local task_name
    task_name=$(get_task_name "$task_id" 2>/dev/null || echo "Task $task_id")

    # Get relevant learnings for context
    local learnings=""
    if type get_learnings_for_phase &>/dev/null; then
        local phase_id="${task_id%%.*}"
        learnings=$(get_learnings_for_phase "$phase_id" 2>/dev/null || true)
    fi

    # Build the prompt - tell Claude to run /cross-team
    local prompt
    prompt="Run /cross-team to execute the next task from the plan.

The next task should be: $task_id - $task_name

Follow the TDD-first workflow:
1. Write all tests first
2. Implement code to make tests pass
3. Spawn the Verifier for approval
4. Iterate until verified"

    # Add learnings if available
    if [[ -n "$learnings" && "$learnings" =~ [^[:space:]] ]]; then
        prompt+="

## Project Learnings (apply when relevant)

${learnings}"
    fi

    # Create temp file for output
    local output_file
    output_file=$(mktemp)

    # Invoke Claude Code CLI
    # --allowedTools includes Task and Skill for VGL subagent spawning
    claude -p "$prompt" \
        --output-format json \
        --allowedTools "Bash,Read,Write,Edit,Glob,Grep,WebFetch,Task,Skill" \
        > "$output_file" 2>&1
    local exit_code=$?

    # Return the output file path (caller parses it)
    echo "$output_file"

    return $exit_code
}

# parse_claude_output - Extract result information from Claude JSON output
# Args: output_file
# Output: Summary line (success/failure + brief description)
# Returns: 0 on success parsing, 1 on failure
parse_claude_output() {
    local output_file="$1"

    if [[ -z "$output_file" || ! -f "$output_file" ]]; then
        echo "Error: No output file"
        return 1
    fi

    if command -v jq &>/dev/null; then
        local result
        local cost_usd
        local error_msg

        result=$(jq -r '.result // empty' "$output_file" 2>/dev/null)
        cost_usd=$(jq -r '.cost_usd // "unknown"' "$output_file" 2>/dev/null)
        error_msg=$(jq -r '.error // empty' "$output_file" 2>/dev/null)

        if [[ -n "$error_msg" ]]; then
            echo "Error: $error_msg"
            return 1
        fi

        if [[ -n "$result" ]]; then
            local summary
            summary=$(echo "$result" | head -1 | cut -c1-100)
            echo "Success: $summary (cost: \$$cost_usd)"
            return 0
        fi

        echo "Completed (cost: \$$cost_usd)"
        return 0
    else
        if grep -qi '"error"' "$output_file" 2>/dev/null; then
            local error_line
            error_line=$(grep -i 'error' "$output_file" | head -1 | cut -c1-100)
            echo "Error: $error_line"
            return 1
        fi

        if [[ -s "$output_file" ]]; then
            echo "Completed (no structured output)"
            return 0
        fi

        echo "Error: Empty output"
        return 1
    fi
}

# check_iteration_duration - Log warning if iteration exceeds 30 minutes
check_iteration_duration() {
    local start_time="$1"
    local now
    now=$(date +%s)
    local elapsed=$((now - start_time))

    if [[ $elapsed -gt $DURATION_ALERT_THRESHOLD ]]; then
        local duration_min=$((elapsed / 60))
        local log_file="${LOG_FILE:-.planning/ralph.log}"
        {
            echo "---"
            echo "DURATION_ALERT"
            echo "Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
            echo "Iteration duration: ${duration_min}m (exceeds 30m threshold)"
        } >> "$log_file"

        echo -e "${INVOKE_YELLOW}Warning: Iteration exceeded 30 minutes (${duration_min}m)${INVOKE_RESET}" >&2
    fi

    return 0
}

# handle_iteration_failure - Process iteration failure with user choice
handle_iteration_failure() {
    local task_id="$1"
    local error_message="$2"

    echo ""
    echo -e "${INVOKE_RED}${INVOKE_BOLD}FAILURE: Task '$task_id' failed${INVOKE_RESET}"
    echo -e "${INVOKE_RED}$error_message${INVOKE_RESET}"
    echo ""

    echo -e "Options:"
    echo -e "  ${INVOKE_YELLOW}r${INVOKE_RESET} - Retry this task"
    echo -e "  ${INVOKE_YELLOW}s${INVOKE_RESET} - Skip and continue to next task"
    echo -e "  ${INVOKE_YELLOW}a${INVOKE_RESET} - Abort ralph loop"
    echo ""

    while true; do
        read -p "Choice [r/s/a]: " choice
        case "$choice" in
            r|R) return 0 ;;
            s|S) return 1 ;;
            a|A) return 2 ;;
            *) echo "Invalid choice. Enter r, s, or a." ;;
        esac
    done
}

# handle_claude_crash - Process non-zero Claude exit
handle_claude_crash() {
    local exit_code="$1"
    local task_id="$2"

    echo ""
    echo -e "${INVOKE_RED}${INVOKE_BOLD}CLAUDE CRASH: Task '$task_id' terminated abnormally${INVOKE_RESET}"
    echo -e "${INVOKE_RED}Claude CLI exited with code: $exit_code${INVOKE_RESET}"
    echo ""
    echo -e "${INVOKE_YELLOW}Aborting ralph loop to prevent further issues.${INVOKE_RESET}"
    echo ""

    return 1
}
