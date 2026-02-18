# Task 1.2: Cascade Evaluator with Multi-Dimensional Metrics

## Goal (from must_haves)
**Truths:**
- CascadeEvaluator.evaluate() runs a 3-stage cascade: collect-only check, partial test run, full test suite
- Stage 1 rejects approaches whose tests cannot even be collected (syntax errors, missing imports)
- Stage 2 runs first 3 tests and rejects if pass_rate < 0.5
- Stage 3 runs the full test command and extracts comprehensive metrics
- Metrics include test_pass_rate, duration_s, complexity, todo_count, error_count, stage, and artifacts
- Artifacts capture test_output and error_trace for feedback into evolution prompts
- CLI supports --evaluate with optional --source-dirs and --timeout

**Artifacts:**
- scripts/evo_eval.py
- tests/python/test_evo_eval.py

## Context
This is the evaluation component of the evolutionary intelligence system. It replaces simple pass/fail test checking with a multi-stage cascade evaluator inspired by OpenEvolve's cascade evaluation pattern (see /home/user/openevolve/openevolve/evaluator.py).

The cascade pattern saves compute by failing fast on obviously broken approaches. Stage 1 is a 2-second syntax/import check. Stage 2 runs a small subset of tests. Only approaches that pass both stages get the full evaluation. This is critical because the Gatekeeper loop may generate many candidate approaches across islands, and full test suites can be expensive.

The evaluator also extracts code metrics (LOC, TODOs, FIXMEs) from source directories to populate the "complexity" feature dimension used by the MAP-Elites grid in evo_db.py.

## Backend Deliverables
Create `scripts/evo_eval.py`:

### CascadeEvaluator Class
```python
class CascadeEvaluator:
    def __init__(self, config=None):
        # Defaults: stage_thresholds=[0.1, 0.5], timeout=300

    def evaluate(self, test_command: str, source_dirs: list = None) -> dict:
        # Stage 1: Quick collection check
        #   Run: pytest --collect-only (with 2s timeout via subprocess)
        #   If exit_code != 0: return {test_pass_rate: 0.0, stage: 1, error: stderr}
        #
        # Stage 2: Partial test run (first 3 tests)
        #   Parse --collect-only output to extract first 3 test names
        #   Run: pytest -x --tb=short -k "test_name1 or test_name2 or test_name3"
        #   Extract pass/fail counts from output
        #   If pass_rate < 0.5: return partial metrics + {stage: 2}
        #
        # Stage 3: Full suite
        #   Run: complete test_command (with timeout)
        #   Extract: tests passed/total, duration
        #   If source_dirs provided: scan for LOC, TODOs, FIXMEs
        #   Return full metrics + {stage: 3}

    def _extract_test_metrics(self, test_output: str) -> dict:
        # Parse pytest output for passed/failed/error/skipped counts
        # Regex patterns:
        #   r'(\d+) passed' -> passed count
        #   r'(\d+) failed' -> failed count
        #   r'(\d+) error'  -> error count
        #   r'in ([\d.]+)s' -> duration
        # Returns {passed, failed, errors, total, pass_rate, duration_s}

    def _extract_code_metrics(self, source_dirs: list) -> dict:
        # Walk source_dirs, count:
        #   - Total lines of code (non-empty, non-comment .py files)
        #   - TODO count (case-insensitive grep)
        #   - FIXME count (case-insensitive grep)
        #   - Complexity estimate: LOC (simple proxy)
        # Returns {complexity, todo_count, fixme_count}

    def _capture_artifacts(self, test_output: str, exit_code: int) -> dict:
        # Structure error traces for prompt feedback
        # Extract traceback blocks from test_output
        # Truncate to reasonable length (max 2000 chars for test_output, 1000 for error_trace)
        # Returns {test_output: str, error_trace: str}
```

### Metrics Schema
```json
{
    "test_pass_rate": 0.75,
    "duration_s": 12.3,
    "complexity": 450,
    "todo_count": 3,
    "error_count": 1,
    "stage": 3,
    "artifacts": {
        "test_output": "...truncated pytest output...",
        "error_trace": "...extracted traceback..."
    }
}
```

### CLI Interface
```bash
python3 evo_eval.py --evaluate "pytest tests/python/test_evo_db.py -v"
python3 evo_eval.py --evaluate "pytest tests/ -v" --source-dirs "scripts,hooks"
python3 evo_eval.py --evaluate "pytest tests/ -v" --source-dirs "scripts" --timeout 120
```
All CLI output is JSON for programmatic consumption.

### Subprocess Execution
- Use `subprocess.run()` with `capture_output=True, text=True, timeout=<seconds>`
- Stage 1 timeout: 2 seconds (collection should be fast)
- Stage 2 timeout: 30 seconds (partial run)
- Stage 3 timeout: configurable (default 300 seconds)
- On `subprocess.TimeoutExpired`: return partial metrics with `{timeout: true}` in artifacts

## Frontend Deliverables
- CLI `--evaluate` outputs full metrics JSON to stdout
- Metrics always include `stage` field indicating how far evaluation progressed
- Artifacts always included (may be empty strings if no errors)

## Tests to Write (TDD-First)

### tests/python/test_evo_eval.py
- test_stage1_rejects_unparseable -- mock subprocess returning syntax error output with exit code 1 -> stage 1 fail with test_pass_rate 0.0
- test_stage1_passes_valid -- mock subprocess returning successful collection output with exit code 0 -> proceeds to stage 2
- test_stage2_rejects_low_pass_rate -- mock subprocess returning 0/3 tests passed -> stage 2 fail with partial metrics
- test_stage2_passes_partial -- mock subprocess returning 2/3 tests passed -> proceeds to stage 3
- test_stage3_full_metrics -- mock subprocess returning all tests passed -> full metrics with stage 3, test_pass_rate 1.0
- test_timeout_handling -- mock subprocess raising TimeoutExpired -> returns partial metrics with timeout artifact
- test_metrics_extraction -- _extract_test_metrics parses "3 passed, 1 failed in 2.5s" into {passed: 3, failed: 1, pass_rate: 0.75, duration_s: 2.5}
- test_code_metrics -- _extract_code_metrics counts LOC, TODOs in fixture .py source files created in tmp_path
- test_artifact_capture -- _capture_artifacts extracts traceback block and truncates long output to max chars
- test_empty_source_dirs -- evaluate with source_dirs=None -> complexity=0, todo_count=0
- test_cli_evaluate -- CLI --evaluate with mocked subprocess outputs valid JSON containing test_pass_rate and stage keys

## Test Dependency Graph

| Test | File | Depends On | Guidance |
|------|------|-----------|----------|
| T1 | tests/python/test_evo_eval.py | -- | Create evo_eval.py with CascadeEvaluator class. Use subprocess for test execution, parse pytest output with regex. Use tmp_path for test fixtures. Mock subprocess.run via unittest.mock.patch for controlled test output at each stage. Reference /home/user/openevolve/openevolve/evaluator.py for cascade pattern (_cascade_evaluate stages). No external deps beyond stdlib. |

Dispatch order:
- Wave 1: T1

## Key Links
- OpenEvolve reference: /home/user/openevolve/openevolve/evaluator.py (cascade evaluation, _cascade_evaluate method)
- Consumer: hooks/stop-hook.sh (calls evo_eval.py --evaluate after failed verification)
- Consumer: agents/executor.md (evaluates island candidates)
- Feeds into: scripts/evo_db.py (metrics stored in Approach.metrics)

## Technical Notes
- Dependencies: stdlib only (subprocess, re, os, json, argparse, time)
- Pytest output parsing is regex-based -- handle both pytest 7.x and 8.x output formats
- The collect-only stage (`pytest --collect-only`) is extremely fast (<1s typically) and catches syntax errors, import failures
- Stage 2 test selection: parse `--collect-only` output for `<Function ...>` patterns, extract first 3 function names
- Code metrics complexity is intentionally simple (LOC count) -- avoids ast/radon dependency
- Artifact truncation prevents enormous error traces from bloating the evolution prompt
- test_pass_rate is the primary fitness metric used by evo_db.py for MAP-Elites cell comparison
