#!/usr/bin/env python3
"""Hotspot profiler for Hyperphase N (evolutionary optimization).

Profiles a test suite with cProfile, extracts slow functions from source
directories, scores them by (time_pct × log(1 + complexity)), and outputs
a ranked JSON array of optimization candidates.

CLI:
    python3 evo_profiler.py --test-command CMD --source-dirs DIRS [--module MODULE] --top-n N

Output:
    JSON array of [{file, function, baseline_ms, time_pct, complexity, test_count, score}]
    sorted by score descending.
"""

import argparse
import ast
import json
import os
import math
import pstats
import re
import subprocess
import sys
import tempfile
from gk_log import gk_error, gk_warn, gk_info


def profile_test_suite(test_command, profile_output):
    """Run test suite under cProfile and save stats to profile_output."""
    # Wrap the test command to run under cProfile
    cmd = [
        sys.executable, "-m", "cProfile",
        "-o", profile_output,
        "-m", "pytest",
    ]
    # Parse extra args from test_command (skip the 'pytest' part if present)
    parts = test_command.split()
    start_idx = 0
    for i, part in enumerate(parts):
        if part in ("pytest", "python3", "python"):
            start_idx = i + 1
            break
    # If command starts with 'pytest', skip it since we use -m pytest
    if parts and parts[0] == "pytest":
        start_idx = 1
    cmd.extend(parts[start_idx:])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,
    )
    gk_info(f"cProfile exit code: {result.returncode}")
    if result.stderr:
        gk_info(f"stderr: {result.stderr[:500]}")
    return result.returncode == 0


def parse_profile_stats(profile_output, source_dirs):
    """Parse cProfile output and extract functions from source_dirs."""
    stats = pstats.Stats(profile_output)
    stats.sort_stats("cumulative")

    total_time = stats.total_tt if stats.total_tt > 0 else 1.0
    functions = []

    for key, (cc, nc, tt, ct, callers) in stats.stats.items():
        filename, lineno, funcname = key
        abs_filename = os.path.abspath(filename)

        # Filter to functions in source_dirs
        in_source = False
        for source_dir in source_dirs:
            abs_source = os.path.abspath(source_dir)
            if abs_filename.startswith(abs_source):
                in_source = True
                break

        if not in_source:
            continue

        # Skip test files and __init__.py
        basename = os.path.basename(filename)
        if basename.startswith("test_") or basename == "__init__.py":
            continue
        if "test" in basename.lower() and basename.endswith(".py"):
            continue

        time_pct = (ct / total_time) * 100.0 if total_time > 0 else 0.0
        baseline_ms = ct * 1000.0

        functions.append({
            "file": filename,
            "function": funcname,
            "baseline_ms": round(baseline_ms, 3),
            "time_pct": round(time_pct, 2),
            "line": lineno,
        })

    return functions


def compute_complexity(file_path, function_name):
    """Compute complexity and detect Taichi kernels.

    Returns dict with 'complexity' (non-blank LOC) and 'is_taichi' (bool).
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except OSError as e:
        gk_warn(f"Cannot read {file_path}: {e}")
        return {"complexity": 0, "is_taichi": False}

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        gk_warn(f"Cannot parse {file_path}: {e}")
        return {"complexity": 0, "is_taichi": False}

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == function_name:
                # Count non-blank lines in the function body
                lines = source.splitlines()
                start = node.lineno - 1
                end = node.end_lineno if hasattr(node, "end_lineno") and node.end_lineno else start + 1
                func_lines = lines[start:end]
                count = 0
                for line in func_lines:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        count += 1

                # Check for Taichi decorators
                is_taichi = False
                try:
                    from evo_taichi_ast import has_any_taichi_decorator
                    is_taichi = has_any_taichi_decorator(node)
                except ImportError:
                    # Fallback: check decorators manually
                    for dec in node.decorator_list:
                        if isinstance(dec, ast.Attribute):
                            if isinstance(dec.value, ast.Name) and dec.value.id == "ti":
                                is_taichi = True
                                break

                return {"complexity": count, "is_taichi": is_taichi}

    return {"complexity": 0, "is_taichi": False}


def estimate_test_count(test_command, function_name):
    """Estimate number of tests that exercise a function using pytest --collect-only."""
    try:
        parts = test_command.split()
        collect_cmd = ["pytest", "--collect-only", "-q"]
        for part in parts[1:]:
            if not part.startswith("-"):
                collect_cmd.append(part)
                break

        result = subprocess.run(
            collect_cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Count test names that mention the function
        count = 0
        for line in result.stdout.splitlines():
            if function_name.lower() in line.lower():
                count += 1
        return max(count, 1)  # At least 1 if the function was profiled
    except subprocess.TimeoutExpired:
        gk_warn(f"pytest --collect-only timed out while estimating test count for {function_name}")
        return 1
    except FileNotFoundError as e:
        gk_warn(f"pytest not found while estimating test count: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(description="Hotspot profiler for Hyperphase N")
    parser.add_argument("--test-command", required=True, help="Test command to profile")
    parser.add_argument("--source-dirs", required=True, help="Comma-separated source directories")
    parser.add_argument("--module", default="", help="Optional module path filter")
    parser.add_argument("--top-n", type=int, default=5, help="Number of top candidates (default: 5)")

    args = parser.parse_args()
    source_dirs = [d.strip() for d in args.source_dirs.split(",")]

    # Profile in a temp file
    with tempfile.NamedTemporaryFile(suffix=".prof", delete=False) as f:
        profile_output = f.name

    try:
        success = profile_test_suite(args.test_command, profile_output)
        if not success or not os.path.exists(profile_output):
            print(json.dumps([{"error": "Profiling failed"}]))
            sys.exit(1)

        functions = parse_profile_stats(profile_output, source_dirs)
    finally:
        if os.path.exists(profile_output):
            os.unlink(profile_output)

    # Filter by module if specified
    if args.module:
        functions = [f for f in functions if args.module in f["file"]]

    # Enrich with complexity, Taichi detection, and test count; compute score
    for func in functions:
        cx = compute_complexity(func["file"], func["function"])
        func["complexity"] = cx["complexity"]
        func["is_taichi"] = cx["is_taichi"]
        func["test_count"] = estimate_test_count(args.test_command, func["function"])
        func["score"] = round(func["time_pct"] * math.log(1 + func["complexity"]), 3)

    # Sort by score descending, take top N
    functions.sort(key=lambda f: f["score"], reverse=True)
    top = functions[:args.top_n]

    print(json.dumps(top, indent=2))


if __name__ == "__main__":
    main()
