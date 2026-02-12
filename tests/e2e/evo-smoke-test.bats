#!/usr/bin/env bats
# End-to-End Evolution Pipeline Smoke Test for GSD-VGL
#
# Exercises the full evolution pipeline: evo_db.py, evo_eval.py,
# evo_prompt.py, evo_pollinator.py using a controlled fixture project.
#
# Fixture: tests/fixtures/evo-project/
# Each test gets its own temp copy to avoid cross-contamination.

setup() {
    # Resolve paths
    BATS_TEST_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")" && pwd)"
    PROJECT_ROOT="$(cd "$BATS_TEST_DIR/../.." && pwd)"
    FIXTURE_DIR="$PROJECT_ROOT/tests/fixtures/evo-project"
    PLUGIN_ROOT="$PROJECT_ROOT"
    SCRIPTS_DIR="$PROJECT_ROOT/scripts"

    # Load bats libraries
    BATS_LIB_DIR="$PROJECT_ROOT/node_modules"
    load "$BATS_LIB_DIR/bats-support/load.bash"
    load "$BATS_LIB_DIR/bats-assert/load.bash"
    load "$BATS_LIB_DIR/bats-file/load.bash"

    # Create a temp copy of the fixture for this test
    TEST_DIR="$(mktemp -d)"
    cp -r "$FIXTURE_DIR/." "$TEST_DIR/"
}

teardown() {
    if [[ -n "${TEST_DIR:-}" ]] && [[ -d "$TEST_DIR" ]]; then
        rm -rf "$TEST_DIR"
    fi
}

# -------------------------------------------------------------------
# Test 1: evo_db.py --add and --sample round-trip
# -------------------------------------------------------------------
@test "evo_db: add a new approach and sample from island 0" {
    local DB_PATH="$TEST_DIR/.planning/evolution/1.1"

    # Add a new approach via CLI
    local NEW_APPROACH='{"id":"a4","prompt_addendum":"New strategy with improved error handling","parent_id":"a3","generation":3,"metrics":{"test_pass_rate":0.8,"complexity":25},"island":0,"feature_coords":[0,0],"task_id":"1.1","task_type":"backend","file_patterns":["src/index.py"],"artifacts":{"test_output":"2 passed, 1 failed","error_trace":""},"timestamp":1700003000,"iteration":4}'
    run python3 "$SCRIPTS_DIR/evo_db.py" --db-path "$DB_PATH" --add "$NEW_APPROACH"
    assert_success
    assert_output --partial '"status": "added"'
    assert_output --partial '"id": "a4"'

    # Sample from island 0 -- should return JSON with "parent" key
    run python3 "$SCRIPTS_DIR/evo_db.py" --db-path "$DB_PATH" --sample 0
    assert_success

    # Verify the output is valid JSON with a "parent" key
    echo "$output" | python3 -c "
import sys, json
data = json.load(sys.stdin)
assert 'parent' in data, 'Missing parent key in sample output'
assert data['parent'] is not None, 'parent should not be None for populated island'
assert 'prompt_addendum' in data['parent'], 'parent should have prompt_addendum'
print('sample output valid')
"
}

# -------------------------------------------------------------------
# Test 2: evo_eval.py cascade evaluator with real pytest
# -------------------------------------------------------------------
@test "evo_eval: cascade evaluator produces test_pass_rate and stage" {
    cd "$TEST_DIR"

    # Run cascade evaluator against the fixture's passing tests
    run python3 "$SCRIPTS_DIR/evo_eval.py" --evaluate "pytest tests/test_index.py -v" --timeout 30
    assert_success

    # Parse JSON output and verify key fields
    echo "$output" | python3 -c "
import sys, json
data = json.load(sys.stdin)
assert 'test_pass_rate' in data, 'Missing test_pass_rate'
assert 'stage' in data, 'Missing stage'
assert data['test_pass_rate'] > 0, f'test_pass_rate should be > 0, got {data[\"test_pass_rate\"]}'
assert data['stage'] >= 1, f'stage should be >= 1, got {data[\"stage\"]}'
print(f'pass_rate={data[\"test_pass_rate\"]}, stage={data[\"stage\"]}')
"
}

# -------------------------------------------------------------------
# Test 3: evo_prompt.py builds evolution context prompt
# -------------------------------------------------------------------
@test "evo_prompt: build prompt contains evolution context sections" {
    local DB_PATH="$TEST_DIR/.planning/evolution/1.1"

    # Build a prompt from the pre-populated evolution data
    run python3 "$SCRIPTS_DIR/evo_prompt.py" --build "$DB_PATH" "1.1" --island 0
    assert_success

    # Verify the prompt contains the expected section headers
    assert_output --partial "## Evolution Context"
    assert_output --partial "## Parent Approach"
    assert_output --partial "## What Went Wrong"
    assert_output --partial "## Inspiration Approaches"
    assert_output --partial "## Your Directive"
}

# -------------------------------------------------------------------
# Test 4: evo_pollinator.py cross-pollinates from completed task
# -------------------------------------------------------------------
@test "evo_pollinator: pollinate migrates approaches from completed task to new task" {
    local SOURCE_DB="$TEST_DIR/.planning/evolution/1.1"
    local TARGET_DB="$TEST_DIR/.planning/evolution/1.2"
    local PLAN_PATH="$TEST_DIR/.claude/plan/plan.yaml"

    # Create the target DB directory (empty)
    mkdir -p "$TARGET_DB"

    # The pollinator needs the source task's approaches to be loadable.
    # It loads approaches from the TARGET db and finds source task approaches there.
    # So we need to copy the source approaches into the target DB first,
    # since the pollinator searches within the target DB for approaches
    # matching the source task_id.
    cp "$SOURCE_DB/approaches.jsonl" "$TARGET_DB/approaches.jsonl"
    cp "$SOURCE_DB/metadata.json" "$TARGET_DB/metadata.json"

    # Run pollination for task 1.2
    run python3 "$SCRIPTS_DIR/evo_pollinator.py" --pollinate "$TARGET_DB" "$PLAN_PATH" "1.2" --threshold 0
    assert_success

    # Parse the result and verify migration happened
    echo "$output" | python3 -c "
import sys, json
data = json.load(sys.stdin)
assert 'migrated' in data, 'Missing migrated key'
assert data['migrated'] > 0, f'Expected migrated > 0, got {data[\"migrated\"]}'
assert '1.1' in data.get('source_tasks', []), 'source_tasks should include 1.1'
print(f'migrated={data[\"migrated\"]}, sources={data[\"source_tasks\"]}')
"
}

# -------------------------------------------------------------------
# Test 5: Full pipeline -- add approaches, get best, build prompt
# -------------------------------------------------------------------
@test "full pipeline: add approaches, get best, build prompt with parent" {
    local DB_PATH="$TEST_DIR/.planning/evolution/pipeline"
    mkdir -p "$DB_PATH"

    # Add 5 approaches with varying scores
    local scores=(0.2 0.4 0.6 0.8 1.0)
    local islands=(0 1 0 1 0)
    for i in $(seq 0 4); do
        local score="${scores[$i]}"
        local island="${islands[$i]}"
        local gen="$i"
        local parent_id="null"
        if [ "$i" -gt 0 ]; then
            parent_id="\"approach-$((i-1))\""
        fi
        local approach_json="{\"id\":\"approach-${i}\",\"prompt_addendum\":\"Strategy ${i} with score ${score}\",\"parent_id\":${parent_id},\"generation\":${gen},\"metrics\":{\"test_pass_rate\":${score},\"complexity\":$((10+i*5))},\"island\":${island},\"feature_coords\":[0,0],\"task_id\":\"1.1\",\"task_type\":\"backend\",\"file_patterns\":[\"src/index.py\"],\"artifacts\":{\"test_output\":\"${i} tests passed\",\"error_trace\":\"\"},\"timestamp\":$((1700000000+i*1000)),\"iteration\":$((i+1))}"

        run python3 "$SCRIPTS_DIR/evo_db.py" --db-path "$DB_PATH" --add "$approach_json"
        assert_success
    done

    # Get the best approach -- should be approach-4 with score 1.0
    run python3 "$SCRIPTS_DIR/evo_db.py" --db-path "$DB_PATH" --best
    assert_success
    echo "$output" | python3 -c "
import sys, json
data = json.load(sys.stdin)
assert data is not None, 'best should not be None'
assert data['metrics']['test_pass_rate'] == 1.0, f'Expected best score 1.0, got {data[\"metrics\"][\"test_pass_rate\"]}'
print(f'best_id={data[\"id\"]}, score={data[\"metrics\"][\"test_pass_rate\"]}')
"

    # Build a prompt from the populated DB
    run python3 "$SCRIPTS_DIR/evo_prompt.py" --build "$DB_PATH" "1.1" --island 0
    assert_success

    # The prompt should contain the parent approach content
    assert_output --partial "## Parent Approach"
    assert_output --partial "Strategy"
    # It should also contain the directive section
    assert_output --partial "## Your Directive"
}
