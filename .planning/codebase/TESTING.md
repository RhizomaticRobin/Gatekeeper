# Testing

## Test Framework Matrix
| Framework | Language | Location | Config | Count |
|-----------|----------|----------|--------|-------|
| pytest | Python | `tests/python/` | `pytest.ini` | ~250 tests |
| bats-core | Bash | `tests/bash/`, `tests/e2e/` | loaded via node_modules | ~100 tests |
| vitest | JavaScript | `tests/node/` | `vitest.config.js` | ~15 tests |

Total: ~385 tests (as of Phase 5 completion).

## Test File Patterns
- **Python:** `tests/python/test_{module}.py` (e.g., `test_plan_utils.py`, `test_evo_db.py`)
- **Bash:** `tests/bash/{feature}.bats` (e.g., `stop-hook.bats`, `file-locking.bats`)
- **E2E Bash:** `tests/e2e/{name}-test.bats` (e.g., `smoke-test.bats`, `evo-smoke-test.bats`)
- **Node:** `tests/node/{module}.test.js` (e.g., `install.test.js`, `smoke.test.js`)

## Test Infrastructure
- **Python conftest:** `tests/python/conftest.py` — Fixtures: `sample_plan`, `plan_file` (tmp_path YAML), `empty_plan`. Adds `scripts/` to sys.path.
- **Bash test_helper:** `tests/bash/test_helper/common-setup.bash` — Exports `PLUGIN_ROOT`, `SCRIPTS_DIR`, `HOOKS_DIR`. Loads bats-support/assert/file. Provides `setup_test_dir()`, `teardown_test_dir()`, `create_sample_plan()`, `create_sample_state()`.
- **Test fixtures:** `tests/fixtures/sample-project/` (plan + tasks), `tests/fixtures/evo-project/` (plan + evolution data + source + tests).
- **Bash fixtures:** `tests/bash/fixtures/sample-plan.yaml`, `sample-state.md`.

## Running Tests
```bash
# All Python tests
pytest tests/python/

# All Bash tests
npx bats tests/bash/ tests/e2e/

# All Node tests
npx vitest run

# Individual test files
pytest tests/python/test_plan_utils.py -v
npx bats tests/bash/stop-hook.bats
npx vitest run tests/node/install.test.js
```

## Test Categories by Module
**Core infrastructure:** test_plan_utils.py (44), test_validate_plan.py (49), test_file_locking.py (10)
**Gatekeeper mechanics:** stop-hook.bats, gk-edge-cases.bats, fetch-completion-token.bats, guard-skills.bats
**Evolutionary intelligence:** test_evo_db.py, test_evo_eval.py, test_evo_prompt.py, test_evo_pollinator.py, test_evo_executor.py, evo-stop-hook.bats, evo-migration.bats
**Feedback loop:** test_run_history.py, test_learnings.py, test_patterns.py, history-integration.bats, learnings-injection.bats
**Branding/UX:** rename-verification.bats, error-messages.bats, onboarding.bats
**E2E:** smoke-test.bats, evo-smoke-test.bats

## Test Conventions
- Python tests use `tmp_path` fixture for isolated file operations
- Bash tests create temp dirs via `mktemp -d` in setup, clean in teardown
- All tests are self-contained (no external network, no Claude CLI calls)
- Python uses `monkeypatch` for env var and function mocking
- Bash uses function overrides and environment manipulation for mocking
