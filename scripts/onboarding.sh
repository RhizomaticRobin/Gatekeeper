#!/usr/bin/env bash
# onboarding.sh — First-run onboarding for EvoGatekeeper
#
# Detects first run by absence of .claude/plan/ directory.
# Shows a welcome message (3 lines max) and creates a marker file.
# Welcome is only shown once per project.
#
# Usage: source this script or run it directly from the project root.

# Determine the project directory: use PWD by default
PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"

# First-run detection: if .claude/plan/ directory exists, skip welcome
if [[ -d "${PROJECT_DIR}/.claude/plan" ]]; then
    exit 0
fi

# First run — show welcome message (3 lines max)
echo "Welcome to EvoGatekeeper! Start with /gsd-vgl:quest to plan your project."
echo "Run /gsd-vgl:help for all available commands."

# Create marker directory so welcome is only shown once
mkdir -p "${PROJECT_DIR}/.claude/plan"

exit 0
