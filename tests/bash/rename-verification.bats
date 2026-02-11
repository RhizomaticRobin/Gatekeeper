#!/usr/bin/env bats

setup() {
    load 'test_helper/common-setup'
}

@test "package.json name field is evogatekeeper" {
    run jq -r '.name' "${PLUGIN_ROOT}/package.json"
    assert_success
    assert_output "evogatekeeper"
}

@test "plugin.json name field is evogatekeeper" {
    run jq -r '.name' "${PLUGIN_ROOT}/.claude-plugin/plugin.json"
    assert_success
    assert_output "evogatekeeper"
}

@test "plugin.json description contains EvoGatekeeper" {
    run jq -r '.description' "${PLUGIN_ROOT}/.claude-plugin/plugin.json"
    assert_success
    assert_output --partial "EvoGatekeeper"
}

@test "marketplace.json top-level name is evogatekeeper" {
    run jq -r '.name' "${PLUGIN_ROOT}/.claude-plugin/marketplace.json"
    assert_success
    assert_output "evogatekeeper"
}

@test "marketplace.json plugins[0].name is evogatekeeper" {
    run jq -r '.plugins[0].name' "${PLUGIN_ROOT}/.claude-plugin/marketplace.json"
    assert_success
    assert_output "evogatekeeper"
}

@test "README.md title contains EvoGatekeeper" {
    run head -5 "${PLUGIN_ROOT}/README.md"
    assert_success
    assert_output --partial "EvoGatekeeper"
}

@test "README.md body references EvoGatekeeper" {
    run grep -c "EvoGatekeeper" "${PLUGIN_ROOT}/README.md"
    assert_success
    # Should have at least a few references
    [[ "${output}" -ge 2 ]]
}

@test "commands/help.md shows EvoGatekeeper branding" {
    run grep -c "EvoGatekeeper" "${PLUGIN_ROOT}/commands/help.md"
    assert_success
    [[ "${output}" -ge 1 ]]
}

@test "commands still use gsd-vgl prefix for backward compatibility" {
    # Verify command names in help.md still reference gsd-vgl: prefix
    run grep -c "gsd-vgl:" "${PLUGIN_ROOT}/commands/help.md"
    assert_success
    # There should be many gsd-vgl: command references
    [[ "${output}" -ge 10 ]]
}

@test "package.json bin field still uses gsd-vgl key" {
    run jq -r '.bin | keys[0]' "${PLUGIN_ROOT}/package.json"
    assert_success
    assert_output "gsd-vgl"
}
