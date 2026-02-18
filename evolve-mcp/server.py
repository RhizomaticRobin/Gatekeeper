#!/usr/bin/env python3
"""Evolve-MCP: FastMCP server wrapping evolutionary optimization tools.

Exposes MAP-Elites population operations, cascade evaluation with timing,
profiling, function extraction/mutation, and novelty checking as MCP tools.

All subprocess calls target scripts in the parent directory's scripts/ folder.
All logging goes to stderr; stdout is reserved for the MCP wire protocol.
"""

from fastmcp import FastMCP
import json
import math
import os
import subprocess
import sys
import tempfile

SERVER_CWD = os.getcwd()
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")

mcp = FastMCP("evolve-mcp")


def _run_script(script_name, args, timeout=300):
    """Run a Python script from SCRIPTS_DIR and return parsed JSON output."""
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, script_name)] + args
    print(f"[evolve-mcp] Running: {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=SERVER_CWD,
    )
    if result.stderr:
        print(f"[evolve-mcp] stderr: {result.stderr[:500]}", file=sys.stderr)
    if result.returncode != 0:
        return {"error": f"Script exited with code {result.returncode}", "stderr": result.stderr[:1000]}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw_output": result.stdout[:2000]}


# ---------------------------------------------------------------------------
# Population tools (wrap evo_db.py)
# ---------------------------------------------------------------------------

@mcp.tool()
def population_sample(db_path: str, island_id: int) -> dict:
    """Sample a parent approach and cross-island inspirations from the MAP-Elites population."""
    return _run_script("evo_db.py", ["--db-path", db_path, "--sample", str(island_id)])


@mcp.tool()
def population_add(db_path: str, approach_json: str) -> dict:
    """Add an evaluated approach to the MAP-Elites population database."""
    return _run_script("evo_db.py", ["--db-path", db_path, "--add", approach_json])


@mcp.tool()
def population_best(db_path: str) -> dict:
    """Return the globally best approach in the population."""
    return _run_script("evo_db.py", ["--db-path", db_path, "--best"])


@mcp.tool()
def population_stats(db_path: str) -> dict:
    """Return MAP-Elites population statistics (size, coverage, per-island bests)."""
    return _run_script("evo_db.py", ["--db-path", db_path, "--stats"])


@mcp.tool()
def population_migrate(db_path: str, src_island: int, dst_island: int) -> dict:
    """Migrate best approaches from src island to dst island (ring topology)."""
    return _run_script("evo_db.py", ["--db-path", db_path, "--migrate", str(src_island), str(dst_island)])


# ---------------------------------------------------------------------------
# Prompt tool (wrap evo_prompt.py)
# ---------------------------------------------------------------------------

@mcp.tool()
def evolution_prompt(db_path: str, task_id: str, island_id: int = 0, mode: str = "general") -> str:
    """Build a 5-section evolution context prompt. mode='speed' uses speed-optimization directives."""
    args = ["--build", db_path, task_id, "--island", str(island_id), "--mode", mode]
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, "evo_prompt.py")] + args
    print(f"[evolve-mcp] Running: {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=SERVER_CWD,
    )
    if result.returncode != 0:
        return f"ERROR: {result.stderr[:1000]}"
    return result.stdout


# ---------------------------------------------------------------------------
# Evaluation tools (wrap evo_eval.py)
# ---------------------------------------------------------------------------

@mcp.tool()
def evaluate_correctness(test_command: str, source_dirs: str = "", timeout: int = 300) -> dict:
    """Run cascade evaluator (stages 1-3). Returns test_pass_rate, duration_s, complexity, artifacts."""
    args = ["--evaluate", test_command, "--timeout", str(timeout)]
    if source_dirs:
        args += ["--source-dirs", source_dirs]
    return _run_script("evo_eval.py", args, timeout=timeout + 30)


@mcp.tool()
def evaluate_timing(test_command: str, function_name: str, module_path: str, baseline_ms: float) -> dict:
    """Run full test suite, then time the target function. Returns speedup_ratio and timing_ms."""
    args = [
        "--evaluate", test_command,
        "--time-function", function_name,
        "--module-path", module_path,
        "--baseline-ms", str(baseline_ms),
    ]
    return _run_script("evo_eval.py", args, timeout=600)


# ---------------------------------------------------------------------------
# Profiling tool (wrap evo_profiler.py)
# ---------------------------------------------------------------------------

@mcp.tool()
def profile_hotspots(test_command: str, source_dirs: str, module_path: str = "", top_n: int = 5) -> list:
    """Profile test suite with cProfile. Returns ranked list of slow functions."""
    args = ["--test-command", test_command, "--source-dirs", source_dirs, "--top-n", str(top_n)]
    if module_path:
        args += ["--module", module_path]
    result = _run_script("evo_profiler.py", args, timeout=600)
    if isinstance(result, list):
        return result
    return [result]  # wrap error dict in list


# ---------------------------------------------------------------------------
# Function extraction/mutation tools (wrap evo_block.py)
# ---------------------------------------------------------------------------

@mcp.tool()
def extract_function(file_path: str, function_name: str) -> str:
    """Extract a named function from a Python file and mark it with EVOLVE-BLOCK-START/END. Returns function source."""
    args = ["--extract", "--file", file_path, "--function", function_name]
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, "evo_block.py")] + args
    print(f"[evolve-mcp] Running: {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=SERVER_CWD,
    )
    if result.returncode != 0:
        return f"ERROR: {result.stderr[:1000]}"
    return result.stdout


@mcp.tool()
def apply_diff(file_path: str, function_name: str, diff: str) -> dict:
    """Apply a SEARCH/REPLACE diff to the named function in a file. Returns {success, applied_code}."""
    # Write diff to a temp file to avoid shell escaping issues
    with tempfile.NamedTemporaryFile(mode="w", suffix=".diff", delete=False) as f:
        f.write(diff)
        diff_file = f.name
    try:
        args = ["--apply-diff", "--file", file_path, "--function", function_name, "--diff-file", diff_file]
        return _run_script("evo_block.py", args, timeout=30)
    finally:
        os.unlink(diff_file)


@mcp.tool()
def replace_function(file_path: str, function_name: str, new_code: str) -> dict:
    """Replace a function body in a file with optimized code. Creates .bak_{timestamp} backup first."""
    # Write new code to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(new_code)
        code_file = f.name
    try:
        args = ["--replace", "--file", file_path, "--function", function_name, "--source-file", code_file]
        return _run_script("evo_block.py", args, timeout=30)
    finally:
        os.unlink(code_file)


@mcp.tool()
def revert_function(file_path: str, function_name: str) -> dict:
    """Restore a function from its most recent .bak_* backup. Returns {success, restored_from}."""
    args = ["--revert", "--file", file_path, "--function", function_name]
    return _run_script("evo_block.py", args, timeout=30)


# ---------------------------------------------------------------------------
# Novelty check (pure Python — no subprocess)
# ---------------------------------------------------------------------------

@mcp.tool()
def check_novelty(candidate_code: str, reference_codes: list[str]) -> dict:
    """Check structural novelty using OpenEvolve heuristic.

    Score = (len_diff × 0.1) + (line_diff × 10) + (char_diff × 0.5)
    where diffs are computed against the closest reference.

    Returns {novelty_score, is_novel} where is_novel = score >= 15.0.
    """
    if not reference_codes:
        return {"novelty_score": 100.0, "is_novel": True}

    candidate_lines = candidate_code.strip().splitlines()
    candidate_len = len(candidate_code)
    candidate_line_count = len(candidate_lines)

    min_score = float("inf")
    for ref in reference_codes:
        if not ref:
            continue
        ref_lines = ref.strip().splitlines()
        ref_len = len(ref)
        ref_line_count = len(ref_lines)

        len_diff = abs(candidate_len - ref_len)
        line_diff = abs(candidate_line_count - ref_line_count)

        # Character-level diff: count chars that differ at each position
        char_diff = 0
        for i in range(max(candidate_line_count, ref_line_count)):
            c_line = candidate_lines[i] if i < candidate_line_count else ""
            r_line = ref_lines[i] if i < ref_line_count else ""
            for j in range(max(len(c_line), len(r_line))):
                c_char = c_line[j] if j < len(c_line) else ""
                r_char = r_line[j] if j < len(r_line) else ""
                if c_char != r_char:
                    char_diff += 1

        score = (len_diff * 0.1) + (line_diff * 10) + (char_diff * 0.5)
        min_score = min(min_score, score)

    if min_score == float("inf"):
        min_score = 100.0

    return {
        "novelty_score": round(min_score, 2),
        "is_novel": min_score >= 15.0,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
