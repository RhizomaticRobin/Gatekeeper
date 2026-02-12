#!/usr/bin/env bats
# evo-migration.bats — tests for task 3.1: Remove static heuristics and update references
# Verifies all 7 old heuristic scripts and tests are deleted, no dangling references remain,
# README has evolutionary intelligence section, and all 4 evo scripts exist.

setup() {
    load 'test_helper/common-setup'
}

# --- Test 1: All 7 old heuristic scripts must NOT exist ---
@test "test_no_deleted_scripts_exist" {
    assert_file_not_exist "${PLUGIN_ROOT}/scripts/wave_sizer.py"
    assert_file_not_exist "${PLUGIN_ROOT}/scripts/task_router.py"
    assert_file_not_exist "${PLUGIN_ROOT}/scripts/failure_classifier.py"
    assert_file_not_exist "${PLUGIN_ROOT}/scripts/budget_scheduler.py"
    assert_file_not_exist "${PLUGIN_ROOT}/scripts/auto_fixer.py"
    assert_file_not_exist "${PLUGIN_ROOT}/scripts/dep_resolver.py"
    assert_file_not_exist "${PLUGIN_ROOT}/scripts/progress_advisor.py"
}

# --- Test 2: All 7 old test files must NOT exist ---
@test "test_no_deleted_tests_exist" {
    assert_file_not_exist "${PLUGIN_ROOT}/tests/python/test_wave_sizer.py"
    assert_file_not_exist "${PLUGIN_ROOT}/tests/python/test_task_router.py"
    assert_file_not_exist "${PLUGIN_ROOT}/tests/python/test_failure_classifier.py"
    assert_file_not_exist "${PLUGIN_ROOT}/tests/python/test_budget_scheduler.py"
    assert_file_not_exist "${PLUGIN_ROOT}/tests/python/test_auto_fixer.py"
    assert_file_not_exist "${PLUGIN_ROOT}/tests/python/test_dep_resolver.py"
    assert_file_not_exist "${PLUGIN_ROOT}/tests/python/test_progress_advisor.py"
}

# --- Test 3: No references to old scripts in scripts/ directory ---
@test "test_no_references_in_scripts" {
    run grep -r --include='*.py' --include='*.sh' --include='*.md' \
        -l 'wave_sizer\|task_router\|failure_classifier\|budget_scheduler\|auto_fixer\|dep_resolver\|progress_advisor' \
        "${PLUGIN_ROOT}/scripts/" 2>/dev/null
    # grep returns 1 when no matches found, which is what we want
    assert_failure
}

# --- Test 4: No references to old scripts in hooks/ directory ---
@test "test_no_references_in_hooks" {
    run grep -r --include='*.sh' --include='*.js' --include='*.json' --include='*.md' \
        -l 'wave_sizer\|task_router\|failure_classifier\|budget_scheduler\|auto_fixer\|dep_resolver\|progress_advisor' \
        "${PLUGIN_ROOT}/hooks/" 2>/dev/null
    # grep returns 1 when no matches found, which is what we want
    assert_failure
}

# --- Test 5: No references to old scripts in agents/ directory ---
@test "test_no_references_in_agents" {
    run grep -r --include='*.md' --include='*.json' \
        -l 'wave_sizer\|task_router\|failure_classifier\|budget_scheduler\|auto_fixer\|dep_resolver\|progress_advisor' \
        "${PLUGIN_ROOT}/agents/" 2>/dev/null
    # grep returns 1 when no matches found, which is what we want
    assert_failure
}

# --- Test 6: README.md contains "evolution" or "evolutionary" (case-insensitive) ---
@test "test_readme_has_evolution" {
    run grep -i 'evolution\|evolutionary' "${PLUGIN_ROOT}/README.md"
    assert_success
}

# --- Test 7: All 4 evo scripts exist ---
@test "test_evo_scripts_exist" {
    assert_file_exist "${PLUGIN_ROOT}/scripts/evo_db.py"
    assert_file_exist "${PLUGIN_ROOT}/scripts/evo_eval.py"
    assert_file_exist "${PLUGIN_ROOT}/scripts/evo_prompt.py"
    assert_file_exist "${PLUGIN_ROOT}/scripts/evo_pollinator.py"
}
