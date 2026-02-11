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
