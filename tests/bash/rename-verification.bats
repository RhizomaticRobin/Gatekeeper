#!/usr/bin/env bats

setup() {
    load 'test_helper/common-setup'
}

@test "package.json name field is gatekeeper" {
    run jq -r '.name' "${PLUGIN_ROOT}/package.json"
    assert_success
    assert_output "gatekeeper"
}

@test "plugin.json name field is gatekeeper" {
    run jq -r '.name' "${PLUGIN_ROOT}/.claude-plugin/plugin.json"
    assert_success
    assert_output "gatekeeper"
}

@test "plugin.json description contains Gatekeeper" {
    run jq -r '.description' "${PLUGIN_ROOT}/.claude-plugin/plugin.json"
    assert_success
    assert_output --partial "Gatekeeper"
}

@test "marketplace.json top-level name is gatekeeper" {
    run jq -r '.name' "${PLUGIN_ROOT}/.claude-plugin/marketplace.json"
    assert_success
    assert_output "gatekeeper"
}

@test "marketplace.json plugins[0].name is gatekeeper" {
    run jq -r '.plugins[0].name' "${PLUGIN_ROOT}/.claude-plugin/marketplace.json"
    assert_success
    assert_output "gatekeeper"
}

@test "README.md title contains Gatekeeper" {
    run head -5 "${PLUGIN_ROOT}/README.md"
    assert_success
    assert_output --partial "Gatekeeper"
}

@test "README.md body references Gatekeeper" {
    run grep -c "Gatekeeper" "${PLUGIN_ROOT}/README.md"
    assert_success
    # Should have at least a few references
    [[ "${output}" -ge 2 ]]
}

@test "commands/help.md shows Gatekeeper branding" {
    run grep -c "Gatekeeper" "${PLUGIN_ROOT}/commands/help.md"
    assert_success
    [[ "${output}" -ge 1 ]]
}

@test "commands still use gatekeeper prefix for backward compatibility" {
    # Verify command names in help.md still reference gatekeeper: prefix
    run grep -c "gatekeeper:" "${PLUGIN_ROOT}/commands/help.md"
    assert_success
    # There should be many gatekeeper: command references
    [[ "${output}" -ge 10 ]]
}

@test "package.json bin field still uses gatekeeper key" {
    run jq -r '.bin | keys[0]' "${PLUGIN_ROOT}/package.json"
    assert_success
    assert_output "gatekeeper"
}
