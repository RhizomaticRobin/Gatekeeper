"""
Evolve MCP tools for Gatekeeper Evolve server.

Wraps MAP-Elites population operations, cascade evaluation with timing,
profiling, function extraction/mutation, novelty checking, and Taichi GPU
kernel profiling/analysis/harness-generation as MCP tools.

All subprocess calls target scripts in the plugin's scripts/ folder via evolve_runner.
"""

import logging
import os
import tempfile
from typing import Optional

from fastmcp import FastMCP
from gatekeeper_evolve_mcp.database import DatabaseManager
from gatekeeper_evolve_mcp import evolve_runner

logger = logging.getLogger(__name__)

_db: Optional[DatabaseManager] = None


def register_tools(mcp: FastMCP, db: DatabaseManager) -> None:
    """Register all evolve tools with FastMCP server."""
    global _db
    _db = db

    # Population tools
    mcp.tool()(population_sample)
    mcp.tool()(population_add)
    mcp.tool()(population_best)
    mcp.tool()(population_stats)
    mcp.tool()(population_migrate)

    # Prompt tool
    mcp.tool()(evolution_prompt)

    # Evaluation tools
    mcp.tool()(evaluate_correctness)
    mcp.tool()(evaluate_timing)

    # Profiling tool
    mcp.tool()(profile_hotspots)

    # Function extraction/mutation tools
    mcp.tool()(extract_function)
    mcp.tool()(apply_diff)
    mcp.tool()(replace_function)
    mcp.tool()(revert_function)
    mcp.tool()(extract_bundle)

    # Taichi GPU tools
    mcp.tool()(taichi_profile)
    mcp.tool()(taichi_analyze)
    mcp.tool()(benchmark_harness_gen)

    # Novelty check (inline)
    mcp.tool()(check_novelty)

    logger.info("Evolve tools registered (18 tools)", extra={'tool_name': 'evolve'})


# ---------------------------------------------------------------------------
# Population tools (wrap evo_db.py)
# ---------------------------------------------------------------------------

def population_sample(db_path: str, island_id: int) -> dict:
    """Sample a parent approach and cross-island inspirations from the MAP-Elites population."""
    return evolve_runner.run_script("evo_db.py", ["--db-path", db_path, "--sample", str(island_id)])


def population_add(db_path: str, approach_json: str) -> dict:
    """Add an evaluated approach to the MAP-Elites population database."""
    return evolve_runner.run_script("evo_db.py", ["--db-path", db_path, "--add", approach_json])


def population_best(db_path: str) -> dict:
    """Return the globally best approach in the population."""
    return evolve_runner.run_script("evo_db.py", ["--db-path", db_path, "--best"])


def population_stats(db_path: str) -> dict:
    """Return MAP-Elites population statistics (size, coverage, per-island bests)."""
    return evolve_runner.run_script("evo_db.py", ["--db-path", db_path, "--stats"])


def population_migrate(db_path: str, src_island: int, dst_island: int) -> dict:
    """Migrate best approaches from src island to dst island (ring topology)."""
    return evolve_runner.run_script("evo_db.py", ["--db-path", db_path, "--migrate", str(src_island), str(dst_island)])


# ---------------------------------------------------------------------------
# Prompt tool (wrap evo_prompt.py)
# ---------------------------------------------------------------------------

def evolution_prompt(db_path: str, task_id: str, island_id: int = 0, mode: str = "general") -> str:
    """Build a 5-section evolution context prompt. mode='speed' for CPU speed, 'taichi' for GPU kernel optimization."""
    args = ["--build", db_path, task_id, "--island", str(island_id), "--mode", mode]
    return evolve_runner.run_script_raw("evo_prompt.py", args, timeout=60)


# ---------------------------------------------------------------------------
# Evaluation tools (wrap evo_eval.py)
# ---------------------------------------------------------------------------

def evaluate_correctness(test_command: str, source_dirs: str = "", timeout: int = 300) -> dict:
    """Run cascade evaluator (stages 1-3). Returns test_pass_rate, duration_s, complexity, artifacts."""
    args = ["--evaluate", test_command, "--timeout", str(timeout)]
    if source_dirs:
        args += ["--source-dirs", source_dirs]
    return evolve_runner.run_script("evo_eval.py", args, timeout=timeout + 30)


def evaluate_timing(test_command: str, function_name: str, module_path: str, baseline_ms: float) -> dict:
    """Run full test suite, then time the target function. Returns speedup_ratio and timing_ms."""
    args = [
        "--evaluate", test_command,
        "--time-function", function_name,
        "--module-path", module_path,
        "--baseline-ms", str(baseline_ms),
    ]
    return evolve_runner.run_script("evo_eval.py", args, timeout=600)


# ---------------------------------------------------------------------------
# Profiling tool (wrap evo_profiler.py)
# ---------------------------------------------------------------------------

def profile_hotspots(test_command: str, source_dirs: str, module_path: str = "", top_n: int = 5) -> list:
    """Profile test suite with cProfile. Returns ranked list of slow functions."""
    args = ["--test-command", test_command, "--source-dirs", source_dirs, "--top-n", str(top_n)]
    if module_path:
        args += ["--module", module_path]
    result = evolve_runner.run_script("evo_profiler.py", args, timeout=600)
    if isinstance(result, list):
        return result
    return [result]


# ---------------------------------------------------------------------------
# Function extraction/mutation tools (wrap evo_block.py)
# ---------------------------------------------------------------------------

def extract_function(file_path: str, function_name: str) -> str:
    """Extract a named function from a Python file and mark it with EVOLVE-BLOCK-START/END. Returns function source."""
    args = ["--extract", "--file", file_path, "--function", function_name]
    return evolve_runner.run_script_raw("evo_block.py", args, timeout=30)


def apply_diff(file_path: str, function_name: str, diff: str) -> dict:
    """Apply a SEARCH/REPLACE diff to the named function in a file. Returns {success, applied_code}."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".diff", delete=False) as f:
        f.write(diff)
        diff_file = f.name
    try:
        args = ["--apply-diff", "--file", file_path, "--function", function_name, "--diff-file", diff_file]
        return evolve_runner.run_script("evo_block.py", args, timeout=30)
    finally:
        os.unlink(diff_file)


def replace_function(file_path: str, function_name: str, new_code: str) -> dict:
    """Replace a function body in a file with optimized code. Creates .bak_{timestamp} backup first."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(new_code)
        code_file = f.name
    try:
        args = ["--replace", "--file", file_path, "--function", function_name, "--source-file", code_file]
        return evolve_runner.run_script("evo_block.py", args, timeout=30)
    finally:
        os.unlink(code_file)


def revert_function(file_path: str, function_name: str) -> dict:
    """Restore a function from its most recent .bak_* backup. Returns {success, restored_from}."""
    args = ["--revert", "--file", file_path, "--function", function_name]
    return evolve_runner.run_script("evo_block.py", args, timeout=30)


def extract_bundle(file_path: str, function_name: str) -> str:
    """Extract a Taichi kernel with all dependencies: decorators, @ti.func helpers, module-level ti.field refs, imports.

    Returns a markdown-formatted bundle with EVOLVE-BUNDLE-START/END markers.
    Use this instead of extract_function when optimizing @ti.kernel or @ti.func targets.
    """
    args = ["--extract-bundle", "--file", file_path, "--function", function_name]
    return evolve_runner.run_script_raw("evo_block.py", args, timeout=30)


# ---------------------------------------------------------------------------
# Taichi GPU kernel tools (wrap evo_taichi_*.py)
# ---------------------------------------------------------------------------

def taichi_profile(setup_code: str, call_code: str, warmup: int = 3, trials: int = 10) -> dict:
    """Profile a Taichi kernel with GPU-aware ti.sync() bracketing.

    setup_code: Python code that initializes Taichi, creates fields/state, imports the kernel.
    call_code: Python expression that invokes the kernel (executed inside the timing loop).
    warmup: Number of warmup iterations before timing (default 3).
    trials: Number of timed iterations (default 10).

    Returns {median_ms, min_ms, max_ms, std_ms, trials, warmup_ms, success}.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(setup_code)
        setup_file = f.name
    try:
        args = [
            "--profile",
            "--setup-file", setup_file,
            "--call-code", call_code,
            "--warmup", str(warmup),
            "--trials", str(trials),
        ]
        return evolve_runner.run_script("evo_taichi_profile.py", args, timeout=600)
    finally:
        os.unlink(setup_file)


def taichi_analyze(file_path: str, function_name: str) -> dict:
    """Analyze a Taichi kernel's structure: decorators, parameter types, helper functions, field references.

    Returns {function_name, is_ti_kernel, is_ti_func, decorators, parameters, helper_funcs, field_refs, thread_range, loc}.
    """
    args = ["--analyze", "--file", file_path, "--function", function_name]
    return evolve_runner.run_script("evo_taichi_analyze.py", args, timeout=30)


def benchmark_harness_gen(file_path: str, function_name: str, target_ms: float = 0.0, template: str = "generic") -> str:
    """Auto-generate a pytest benchmark test for a Taichi kernel.

    file_path: Path to the file containing the kernel.
    function_name: Name of the kernel function.
    target_ms: Timing target in milliseconds (0 = no assertion, just measure).
    template: Setup template — 'generic' generates a minimal ti.init() + TODO scaffold.

    Returns generated pytest test file content with ti.sync() bracketing for GPU-accurate timing.
    """
    args = [
        "--harness",
        "--file", file_path,
        "--function", function_name,
        "--target-ms", str(target_ms),
        "--template", template,
    ]
    return evolve_runner.run_script_raw("evo_taichi_harness.py", args, timeout=30)


# ---------------------------------------------------------------------------
# Novelty check (pure Python — no subprocess)
# ---------------------------------------------------------------------------

def check_novelty(candidate_code: str, reference_codes: list[str]) -> dict:
    """Check structural novelty using OpenEvolve heuristic.

    Score = (len_diff * 0.1) + (line_diff * 10) + (char_diff * 0.5)
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
