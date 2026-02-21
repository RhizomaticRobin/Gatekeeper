setup() {
    load 'test_helper/common-setup'
}

@test "bats works" {
    run echo "hello"
    assert_success
    assert_output "hello"
}

@test "common-setup provides PLUGIN_ROOT" {
    [ -n "$PLUGIN_ROOT" ]
}

# === Task 3.2 Tests: help.md and template consistency ===

@test "help_no_deprecated_commands: help.md does not mention new-project" {
    local count
    count=$(grep -ci "new-project" "$PLUGIN_ROOT/commands/help.md" || true)
    [ "$count" -eq 0 ]
}

@test "help_no_deprecated_commands: help.md does not mention autopilot" {
    local count
    count=$(grep -ci "autopilot" "$PLUGIN_ROOT/commands/help.md" || true)
    [ "$count" -eq 0 ]
}

@test "execute_phase_no_ralph: execute-phase.md does not reference ralph" {
    local count
    count=$(grep -ci "ralph" "$PLUGIN_ROOT/workflows/execute-phase.md" || true)
    [ "$count" -eq 0 ]
}

# === Task 4.1 Tests: Delete System 1 files and update package.json ===

# T1: Verify deleted files are gone
@test "deleted_files_gone: bin/ralph.sh does not exist" {
    assert_file_not_exist "$PLUGIN_ROOT/bin/ralph.sh"
}

@test "deleted_files_gone: bin/lib/ directory does not exist" {
    [ ! -d "$PLUGIN_ROOT/bin/lib" ]
}

@test "deleted_files_gone: commands/new-project.md does not exist" {
    assert_file_not_exist "$PLUGIN_ROOT/commands/new-project.md"
}

@test "deleted_files_gone: commands/autopilot.md does not exist" {
    assert_file_not_exist "$PLUGIN_ROOT/commands/autopilot.md"
}

@test "deleted_files_gone: commands/cross.md does not exist" {
    assert_file_not_exist "$PLUGIN_ROOT/commands/cross.md"
}

@test "deleted_files_gone: templates/state.md does not exist" {
    assert_file_not_exist "$PLUGIN_ROOT/templates/state.md"
}

@test "deleted_files_gone: templates/roadmap.md does not exist" {
    assert_file_not_exist "$PLUGIN_ROOT/templates/roadmap.md"
}

@test "deleted_files_gone: templates/config.json does not exist" {
    assert_file_not_exist "$PLUGIN_ROOT/templates/config.json"
}

@test "deleted_files_gone: templates/requirements.md does not exist" {
    assert_file_not_exist "$PLUGIN_ROOT/templates/requirements.md"
}

@test "deleted_files_gone: scripts/learnings.py does not exist" {
    assert_file_not_exist "$PLUGIN_ROOT/scripts/learnings.py"
}

# T2: Verify bin/ directory only contains expected files
@test "bin_dir_minimal: bin/ contains only install.js, install-lib.js, evolve-mcp.sh" {
    local files
    files=$(ls -1 "$PLUGIN_ROOT/bin/" | sort)
    local expected
    expected=$(printf "evolve-mcp.sh\ninstall-lib.js\ninstall.js")
    [ "$files" = "$expected" ]
}

# T3: Verify package.json files array does not contain "bin"
@test "package_json_no_bin: files array does not include bin" {
    run python3 -c "
import json, sys
with open('$PLUGIN_ROOT/package.json') as f:
    pkg = json.load(f)
files_arr = pkg.get('files', [])
for entry in files_arr:
    if entry.strip('/') == 'bin':
        print('FOUND bin in files array')
        sys.exit(1)
print('OK')
"
    assert_success
    assert_output "OK"
}

# T4: Verify guard-skills.sh has no deprecated references
@test "guard_skills_no_deprecated: guard-skills.sh does not allow /cross alias" {
    # The guard should not have a special case for bare "cross" skill
    local count
    count=$(grep -c '"cross"' "$PLUGIN_ROOT/hooks/guard-skills.sh" || true)
    [ "$count" -eq 0 ]
}

@test "guard_skills_no_deprecated: guard-skills.sh does not reference autopilot" {
    local count
    count=$(grep -ci 'autopilot' "$PLUGIN_ROOT/hooks/guard-skills.sh" || true)
    [ "$count" -eq 0 ]
}

# T4 continued: Verify no dangling references to deleted files in source
@test "no_dangling_references: no ralph references in surviving source files" {
    # Exclude tests/, .planning/, .claude/plan/tasks/, README.md
    local count
    count=$(grep -ri 'ralph' "$PLUGIN_ROOT" \
        --include='*.sh' --include='*.js' --include='*.py' --include='*.md' --include='*.json' \
        --exclude-dir=tests --exclude-dir=.planning --exclude-dir='.claude' \
        --exclude-dir='node_modules' \
        --exclude='README.md' \
        -l 2>/dev/null | wc -l || true)
    [ "$count" -eq 0 ]
}

@test "no_dangling_references: no source bin/lib references in surviving files" {
    local count
    count=$(grep -ri 'bin/lib/' "$PLUGIN_ROOT" \
        --include='*.sh' --include='*.js' --include='*.py' --include='*.json' \
        --exclude-dir=tests --exclude-dir=.planning --exclude-dir='.claude' \
        --exclude-dir='node_modules' \
        -l 2>/dev/null | wc -l || true)
    [ "$count" -eq 0 ]
}
