#!/usr/bin/env python3
"""Cascade evaluator with multi-dimensional metrics.

Provides a 3-stage evaluation cascade inspired by OpenEvolve's evaluator.py:
  Stage 1: Quick collection check (pytest --collect-only, 2s timeout)
  Stage 2: Partial test run (first 3 tests, 30s timeout)
  Stage 3: Full test suite (configurable timeout, default 300s)

Each stage fails fast to save compute on broken approaches.

Usage:
  python3 evo_eval.py --evaluate "pytest tests/ -v"
  python3 evo_eval.py --evaluate "pytest tests/ -v" --source-dirs "scripts,hooks"
  python3 evo_eval.py --evaluate "pytest tests/ -v" --source-dirs "scripts" --timeout 120
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time


class CascadeEvaluator:
    """Multi-stage cascade evaluator for test suites.

    Runs a 3-stage cascade:
      1. collect-only check (syntax/import validation)
      2. partial test run (first 3 tests, pass_rate >= 0.5 required)
      3. full test suite with comprehensive metrics

    Attributes:
        stage_thresholds: List of [stage1_threshold, stage2_threshold].
        timeout: Maximum seconds for the full test run (stage 3).
    """

    def __init__(self, config=None):
        config = config or {}
        self.stage_thresholds = config.get("stage_thresholds", [0.1, 0.5])
        self.timeout = config.get("timeout", 300)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, test_command, source_dirs=None):
        """Run 3-stage cascade evaluation.

        Args:
            test_command: The pytest command to run (e.g. "pytest tests/ -v").
            source_dirs: Optional list of directories to scan for code metrics.

        Returns:
            dict with keys: test_pass_rate, duration_s, complexity, todo_count,
            error_count, stage, artifacts.
        """
        # --- Stage 1: collect-only check ---
        try:
            stage1_result = self._run_stage1(test_command)
        except subprocess.TimeoutExpired:
            return self._timeout_result(stage=1)

        if stage1_result["exit_code"] != 0:
            artifacts = self._capture_artifacts(
                stage1_result["stdout"] + "\n" + stage1_result["stderr"],
                stage1_result["exit_code"],
            )
            return {
                "test_pass_rate": 0.0,
                "duration_s": 0.0,
                "complexity": 0,
                "todo_count": 0,
                "error_count": 1,
                "stage": 1,
                "artifacts": artifacts,
            }

        # --- Stage 2: partial test run (first 3 tests) ---
        test_names = self._parse_collected_tests(stage1_result["stdout"])
        try:
            stage2_result = self._run_stage2(test_command, test_names[:3])
        except subprocess.TimeoutExpired:
            return self._timeout_result(stage=2)

        stage2_metrics = self._extract_test_metrics(stage2_result["stdout"])
        stage2_pass_rate = stage2_metrics.get("pass_rate", 0.0)

        if stage2_pass_rate < self.stage_thresholds[1]:
            artifacts = self._capture_artifacts(
                stage2_result["stdout"], stage2_result["exit_code"]
            )
            return {
                "test_pass_rate": stage2_pass_rate,
                "duration_s": stage2_metrics.get("duration_s", 0.0),
                "complexity": 0,
                "todo_count": 0,
                "error_count": stage2_metrics.get("errors", 0)
                + stage2_metrics.get("failed", 0),
                "stage": 2,
                "artifacts": artifacts,
            }

        # --- Stage 3: full test suite ---
        try:
            stage3_result = self._run_stage3(test_command)
        except subprocess.TimeoutExpired:
            return self._timeout_result(stage=3)

        stage3_metrics = self._extract_test_metrics(stage3_result["stdout"])

        # Code metrics
        code_metrics = self._extract_code_metrics(source_dirs) if source_dirs else {
            "complexity": 0,
            "todo_count": 0,
            "fixme_count": 0,
        }

        artifacts = self._capture_artifacts(
            stage3_result["stdout"], stage3_result["exit_code"]
        )

        return {
            "test_pass_rate": stage3_metrics.get("pass_rate", 0.0),
            "duration_s": stage3_metrics.get("duration_s", 0.0),
            "complexity": code_metrics.get("complexity", 0),
            "todo_count": code_metrics.get("todo_count", 0),
            "error_count": stage3_metrics.get("errors", 0)
            + stage3_metrics.get("failed", 0),
            "stage": 3,
            "artifacts": artifacts,
        }

    # ------------------------------------------------------------------
    # Stage runners
    # ------------------------------------------------------------------

    def _run_stage1(self, test_command):
        """Run pytest --collect-only with 2s timeout."""
        # Extract the base pytest command parts, replace with --collect-only
        parts = test_command.split()
        # Build collect-only command: keep pytest and test path, add --collect-only
        collect_cmd = [parts[0], "--collect-only"]
        # Add any test path arguments (not flags)
        for part in parts[1:]:
            if not part.startswith("-"):
                collect_cmd.append(part)
                break

        result = subprocess.run(
            " ".join(collect_cmd),
            shell=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }

    def _run_stage2(self, test_command, test_names):
        """Run first N tests with 30s timeout."""
        if not test_names:
            # No tests found, run the full command but with short timeout
            result = subprocess.run(
                test_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
            }

        # Build -k filter for selected tests
        k_filter = " or ".join(test_names)

        parts = test_command.split()
        # Insert -k filter: pytest <path> -k "test1 or test2 or test3" ...
        partial_cmd = [parts[0]]
        for part in parts[1:]:
            if not part.startswith("-"):
                partial_cmd.append(part)
                break
        partial_cmd.extend(["-x", "--tb=short", "-k", f"'{k_filter}'"])

        result = subprocess.run(
            " ".join(partial_cmd),
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }

    def _run_stage3(self, test_command):
        """Run the full test command with configurable timeout."""
        result = subprocess.run(
            test_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }

    # ------------------------------------------------------------------
    # Metrics extraction
    # ------------------------------------------------------------------

    def _extract_test_metrics(self, test_output):
        """Parse pytest output for pass/fail/error counts and duration.

        Args:
            test_output: Raw pytest stdout string.

        Returns:
            dict with keys: passed, failed, errors, total, pass_rate, duration_s.
        """
        passed = 0
        failed = 0
        errors = 0

        # Match patterns like "3 passed", "1 failed", "1 error"
        m_passed = re.search(r"(\d+)\s+passed", test_output)
        m_failed = re.search(r"(\d+)\s+failed", test_output)
        m_errors = re.search(r"(\d+)\s+error", test_output)

        if m_passed:
            passed = int(m_passed.group(1))
        if m_failed:
            failed = int(m_failed.group(1))
        if m_errors:
            errors = int(m_errors.group(1))

        total = passed + failed + errors

        # Duration: "in 2.50s" or "in 12.34s"
        duration_s = 0.0
        m_duration = re.search(r"in\s+([\d.]+)s", test_output)
        if m_duration:
            duration_s = float(m_duration.group(1))

        pass_rate = passed / total if total > 0 else 0.0

        return {
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "total": total,
            "pass_rate": pass_rate,
            "duration_s": duration_s,
        }

    def _extract_code_metrics(self, source_dirs):
        """Walk source directories and count LOC, TODOs, FIXMEs in .py files.

        Args:
            source_dirs: List of directory paths to scan.

        Returns:
            dict with keys: complexity (LOC count), todo_count, fixme_count.
        """
        if not source_dirs:
            return {"complexity": 0, "todo_count": 0, "fixme_count": 0}

        loc = 0
        todo_count = 0
        fixme_count = 0

        for source_dir in source_dirs:
            if not os.path.isdir(source_dir):
                continue
            for root, _dirs, files in os.walk(source_dir):
                for fname in files:
                    if not fname.endswith(".py"):
                        continue
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                            for line in f:
                                stripped = line.strip()
                                if stripped:  # non-empty line
                                    loc += 1
                                # Case-insensitive TODO/FIXME search
                                line_upper = line.upper()
                                if "TODO" in line_upper:
                                    todo_count += 1
                                if "FIXME" in line_upper:
                                    fixme_count += 1
                    except OSError as e:
                        print(f"[evo_eval] WARN: Cannot read {fpath}: {e}", file=sys.stderr)
                        continue

        return {
            "complexity": loc,
            "todo_count": todo_count,
            "fixme_count": fixme_count,
        }

    def _capture_artifacts(self, test_output, exit_code):
        """Extract and truncate artifacts for prompt feedback.

        Args:
            test_output: Raw test output string.
            exit_code: Process exit code.

        Returns:
            dict with keys: test_output (max 2000 chars), error_trace (max 1000 chars).
        """
        # Truncate test_output to 2000 chars
        truncated_output = test_output[:2000] if len(test_output) > 2000 else test_output

        # Extract traceback blocks
        error_trace = ""
        if exit_code != 0:
            # Find all traceback blocks
            tb_pattern = r"(Traceback \(most recent call last\):.*?)(?=\n\S|\Z)"
            matches = re.findall(tb_pattern, test_output, re.DOTALL)
            if matches:
                error_trace = "\n".join(matches)
            else:
                # Fallback: look for lines with common error patterns
                error_lines = []
                for line in test_output.splitlines():
                    if any(kw in line for kw in ["Error", "FAILED", "error", "Exception"]):
                        error_lines.append(line)
                error_trace = "\n".join(error_lines)
                if not error_trace:
                    print(f"[evo_eval] WARN: Process exited {exit_code} but no traceback or error pattern found in output", file=sys.stderr)

        # Truncate error_trace to 1000 chars
        if len(error_trace) > 1000:
            error_trace = error_trace[:1000]

        return {
            "test_output": truncated_output,
            "error_trace": error_trace,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_collected_tests(self, collect_output):
        """Parse pytest --collect-only output for test function names.

        Args:
            collect_output: Output from pytest --collect-only.

        Returns:
            List of test function names (e.g. ["test_alpha", "test_beta"]).
        """
        pattern = r"<Function\s+(\w+)>"
        return re.findall(pattern, collect_output)

    def _timeout_result(self, stage):
        """Build a result dict for a timeout at the given stage."""
        return {
            "test_pass_rate": 0.0,
            "duration_s": 0.0,
            "complexity": 0,
            "todo_count": 0,
            "error_count": 0,
            "stage": stage,
            "artifacts": {
                "test_output": "",
                "error_trace": "",
                "timeout": True,
            },
        }


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def main():
    """CLI entry point for evo_eval.py."""
    parser = argparse.ArgumentParser(
        description="Cascade evaluator with multi-dimensional metrics"
    )
    parser.add_argument(
        "--evaluate",
        type=str,
        required=True,
        help="Test command to evaluate (e.g. 'pytest tests/ -v')",
    )
    parser.add_argument(
        "--source-dirs",
        type=str,
        default=None,
        help="Comma-separated list of source directories for code metrics",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout in seconds for the full test run (default: 300)",
    )
    parser.add_argument(
        "--time-function",
        type=str,
        default=None,
        help="Function name to time for speedup measurement",
    )
    parser.add_argument(
        "--module-path",
        type=str,
        default=None,
        help="Module path containing the function to time",
    )
    parser.add_argument(
        "--baseline-ms",
        type=float,
        default=None,
        help="Baseline timing in milliseconds for speedup calculation",
    )

    args = parser.parse_args()

    config = {"timeout": args.timeout}
    evaluator = CascadeEvaluator(config=config)

    source_dirs = None
    if args.source_dirs:
        source_dirs = [d.strip() for d in args.source_dirs.split(",")]

    result = evaluator.evaluate(args.evaluate, source_dirs=source_dirs)

    # Timing stage: measure function speedup if all three timing args provided
    if (args.time_function and args.module_path and args.baseline_ms is not None
            and result.get("test_pass_rate", 0.0) == 1.0
            and result.get("stage") == 3):
        timing_result = _measure_function_timing(
            args.time_function, args.module_path, args.baseline_ms
        )
        result.update(timing_result)

    print(json.dumps(result, indent=2))


def _measure_function_timing(function_name, module_path, baseline_ms):
    """Measure function timing via timeit subprocess.

    Runs 5 repetitions, takes median, computes speedup_ratio.

    Args:
        function_name: Name of the function to time.
        module_path: Python module path (e.g., 'src/utils.py').
        baseline_ms: Baseline timing in milliseconds.

    Returns:
        dict with speedup_ratio and timing_ms, or error info.
    """
    # Convert file path to module import path
    mod_path = module_path.replace("/", ".").replace("\\", ".")
    if mod_path.endswith(".py"):
        mod_path = mod_path[:-3]

    # Build timeit command: import the module and call the function
    setup_code = f"from {mod_path} import {function_name}"
    stmt_code = f"{function_name}()"

    timings = []
    for _ in range(5):
        cmd = [
            sys.executable, "-m", "timeit",
            "-n", "1", "-r", "1",
            "-s", setup_code,
            stmt_code,
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if proc.returncode != 0:
                continue
            # Parse timeit output: "1 loop, best of 1: X.XX msec per loop" or similar
            output = proc.stdout.strip()
            # Try multiple formats
            m = re.search(r"([\d.]+)\s*(msec|usec|sec)\s*per loop", output)
            if m:
                val = float(m.group(1))
                unit = m.group(2)
                if unit == "usec":
                    val /= 1000.0
                elif unit == "sec":
                    val *= 1000.0
                timings.append(val)
        except subprocess.TimeoutExpired:
            print(f"[evo_eval] WARN: timeit timed out for {function_name} (rep {_ + 1}/5)", file=sys.stderr)
            continue

    if not timings:
        return {
            "speedup_ratio": 0.0,
            "timing_ms": 0.0,
            "timing_error": "Could not measure function timing",
        }

    # Median timing
    timings.sort()
    median_ms = timings[len(timings) // 2]
    speedup_ratio = baseline_ms / (median_ms + 1e-9)

    return {
        "speedup_ratio": round(speedup_ratio, 4),
        "timing_ms": round(median_ms, 4),
    }


if __name__ == "__main__":
    main()
