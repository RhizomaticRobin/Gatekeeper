#!/usr/bin/env python3
"""Evolve-MCP v2: Full agentic MCP server.

Extends v1 with agent spawning tools that handle all LLM interactions.
Every token generation goes through MCP tools - no direct Task spawning
from commands.

Architecture:
                    ┌─────────────────────────────────────┐
                    │         Command (hyperphase)        │
                    │   Only calls MCP tools, no Task()   │
                    └──────────────┬──────────────────────┘
                                   │ MCP tool calls only
                                   ▼
                    ┌─────────────────────────────────────┐
                    │         Evolve-MCP Server           │
                    │                                     │
                    │  ┌─────────────────────────────┐   │
                    │  │   Procedural Tools (v1)     │   │
                    │  │   - profile_hotspots        │   │
                    │  │   - evaluate_timing         │   │
                    │  │   - population_*            │   │
                    │  │   - extract/replace/revert  │   │
                    │  └─────────────────────────────┘   │
                    │                                     │
                    │  ┌─────────────────────────────┐   │
                    │  │   Agentic Tools (v2)        │   │
                    │  │   - scout_hotspots          │   │
                    │  │   - analyze_novelty         │   │
                    │  │   - diagnose_failures       │   │
                    │  │   - analyze_timing          │   │
                    │  │   - fuse_scout_results      │   │
                    │  │   - optimize_function       │   │
                    │  │   - create_plan             │   │
                    │  └─────────────────────────────┘   │
                    │                                     │
                    │  ┌─────────────────────────────┐   │
                    │  │   LLM Backend               │   │
                    │  │   - Anthropic Claude API    │   │
                    │  │   - (Future: OpenAI, etc)   │   │
                    │  └─────────────────────────────┘   │
                    └─────────────────────────────────────┘
"""

import os
import sys
import json
import asyncio
import subprocess
from typing import Optional
from dataclasses import dataclass, asdict
from datetime import datetime

from fastmcp import FastMCP
import anthropic

# Import v1 tools
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
SERVER_CWD = os.getcwd()

mcp = FastMCP("evolve-mcp-v2")

# ---------------------------------------------------------------------------
# LLM Backend Configuration
# ---------------------------------------------------------------------------

@dataclass
class LLMConfig:
    model: str = "claude-sonnet-4-20250514"  # Default model for agents
    haiku_model: str = "claude-haiku-3-5-20241022"  # Faster model for simple tasks
    opus_model: str = "claude-opus-4-20250514"  # Most capable model
    max_tokens: int = 4096
    temperature: float = 0.7

llm_config = LLMConfig()
client = anthropic.Anthropic()


def _call_llm(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> str:
    """Call Claude API with prompts, return response text."""
    model = model or llm_config.model
    max_tokens = max_tokens or llm_config.max_tokens
    temperature = temperature or llm_config.temperature

    try:
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text
    except Exception as e:
        return f"ERROR: LLM call failed: {str(e)}"


def _run_script(script_name: str, args: list, timeout: int = 300) -> dict:
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
    if result.returncode != 0:
        return {"error": f"Script exited with code {result.returncode}", "stderr": result.stderr[:1000]}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw_output": result.stdout[:2000]}


# ---------------------------------------------------------------------------
# v1 Procedural Tools (preserved for backward compatibility)
# ---------------------------------------------------------------------------

@mcp.tool()
def profile_hotspots(test_command: str, source_dirs: str, module_path: str = "", top_n: int = 5) -> list:
    """Profile test suite with cProfile. Returns ranked list of slow functions."""
    args = ["--test-command", test_command, "--source-dirs", source_dirs, "--top-n", str(top_n)]
    if module_path:
        args += ["--module", module_path]
    result = _run_script("evo_profiler.py", args, timeout=600)
    return result if isinstance(result, list) else [result]


@mcp.tool()
def population_sample(db_path: str, island_id: int) -> dict:
    """Sample a parent approach from MAP-Elites population."""
    return _run_script("evo_db.py", ["--db-path", db_path, "--sample", str(island_id)])


@mcp.tool()
def population_add(db_path: str, approach_json: str) -> dict:
    """Add an evaluated approach to the population."""
    return _run_script("evo_db.py", ["--db-path", db_path, "--add", approach_json])


@mcp.tool()
def population_best(db_path: str) -> dict:
    """Return the globally best approach in the population."""
    return _run_script("evo_db.py", ["--db-path", db_path, "--best"])


@mcp.tool()
def population_stats(db_path: str) -> dict:
    """Return MAP-Elites population statistics."""
    return _run_script("evo_db.py", ["--db-path", db_path, "--stats"])


@mcp.tool()
def population_migrate(db_path: str, src_island: int, dst_island: int) -> dict:
    """Migrate best approaches between islands."""
    return _run_script("evo_db.py", ["--db-path", db_path, "--migrate", str(src_island), str(dst_island)])


@mcp.tool()
def evaluate_correctness(test_command: str, source_dirs: str = "", timeout: int = 300) -> dict:
    """Run cascade evaluator (stages 1-3)."""
    args = ["--evaluate", test_command, "--timeout", str(timeout)]
    if source_dirs:
        args += ["--source-dirs", source_dirs]
    return _run_script("evo_eval.py", args, timeout=timeout + 30)


@mcp.tool()
def evaluate_timing(test_command: str, function_name: str, module_path: str, baseline_ms: float) -> dict:
    """Run tests and time the target function."""
    args = [
        "--evaluate", test_command,
        "--time-function", function_name,
        "--module-path", module_path,
        "--baseline-ms", str(baseline_ms),
    ]
    return _run_script("evo_eval.py", args, timeout=600)


@mcp.tool()
def extract_function(file_path: str, function_name: str) -> str:
    """Extract a named function from a Python file."""
    args = ["--extract", "--file", file_path, "--function", function_name]
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, "evo_block.py")] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=SERVER_CWD)
    return result.stdout if result.returncode == 0 else f"ERROR: {result.stderr}"


@mcp.tool()
def replace_function(file_path: str, function_name: str, new_code: str) -> dict:
    """Replace a function body in a file with optimized code."""
    import tempfile
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
    """Restore a function from its most recent backup."""
    args = ["--revert", "--file", file_path, "--function", function_name]
    return _run_script("evo_block.py", args, timeout=30)


@mcp.tool()
def check_novelty(candidate_code: str, reference_codes: list) -> dict:
    """Check structural novelty using heuristic."""
    if not reference_codes:
        return {"novelty_score": 100.0, "is_novel": True}

    candidate_lines = candidate_code.strip().splitlines()
    min_score = float("inf")

    for ref in reference_codes:
        if not ref:
            continue
        ref_lines = ref.strip().splitlines()
        len_diff = abs(len(candidate_code) - len(ref))
        line_diff = abs(len(candidate_lines) - len(ref_lines))

        char_diff = sum(
            1 for i in range(max(len(candidate_lines), len(ref_lines)))
            for j in range(max(
                len(candidate_lines[i]) if i < len(candidate_lines) else 0,
                len(ref_lines[i]) if i < len(ref_lines) else 0
            ))
            if (candidate_lines[i][j] if i < len(candidate_lines) and j < len(candidate_lines[i]) else "") !=
               (ref_lines[i][j] if i < len(ref_lines) and j < len(ref_lines[i]) else "")
        )

        score = (len_diff * 0.1) + (line_diff * 10) + (char_diff * 0.5)
        min_score = min(min_score, score)

    return {"novelty_score": round(min_score if min_score != float("inf") else 100.0, 2), "is_novel": min_score >= 15.0}


# ---------------------------------------------------------------------------
# v2 Agentic Tools - All LLM calls through these tools
# ---------------------------------------------------------------------------

# Agent system prompts (loaded from agent definition files)
AGENT_PROMPTS = {
    "hotspot-scout": """You are a performance analysis agent. Your job is to identify optimization candidates through DEEP CODE UNDERSTANDING, not just statistical profiling.

You combine:
1. Static analysis (reading code, understanding algorithms)
2. Dynamic profiling (if available)
3. Domain knowledge (known anti-patterns, complexity classes)

Output your findings as JSON.""",

    "novelty-checker": """You are a semantic code analyzer. Your job is to determine whether a candidate code change represents GENUINE ALGORITHMIC NOVELTY or just cosmetic restructuring.

Unlike procedural diff tools, you understand:
1. ALGORITHMIC equivalence (bubble sort vs quick sort)
2. DATA STRUCTURE changes (array vs hash table)
3. OPTIMIZATION techniques (memoization, vectorization)

Output your analysis as JSON.""",

    "correctness-evaluator": """You are a test failure diagnostician. Your job is to understand WHY tests fail after optimization, not just report THAT they failed.

You provide:
1. ROOT CAUSE analysis
2. DIFFERENTIAL DIAGNOSIS
3. FIX SUGGESTIONS
4. REGRESSION RISK assessment

Output your diagnosis as JSON.""",

    "timing-analyzer": """You are a performance timing analyst. Your job is to understand WHY code became faster, not just measure THAT it became faster.

You explain:
1. WHICH operations were eliminated or optimized
2. WHERE in the code the savings occurred
3. SECONDARY effects (cache behavior, memory bandwidth)
4. PREDICTIONS for scaling behavior

Output your analysis as JSON.""",

    "hotspot-fusion": """You are a synthesis agent. Your job is to COMBINE and RECONCILE insights from multiple parallel analysis agents into a unified, actionable recommendation.

You receive outputs from:
- Static Scout (algorithmic complexity)
- Dynamic Scout (runtime profiling)
- Pattern Scout (anti-pattern detection)
- Memory Scout (allocation patterns)

Output unified ranked recommendations as JSON.""",

    "evo-optimizer": """You are an evolutionary optimizer agent. Your job is to generate improved versions of a function that maintain correctness while improving performance.

You receive:
- The original function code
- Analysis of what makes it slow
- Strategy hints for optimization
- Previous attempts (to avoid repetition)

Output the optimized function code.""",

    "strategy-planner": """You are an optimization strategy planner. Your job is to analyze a function and propose specific, actionable optimization approaches.

For each function, propose 2-3 approaches with:
- Description
- Estimated speedup
- Risk level
- Implementation complexity

Output your strategy as JSON.""",
}


@mcp.tool()
def scout_hotspots(
    source_dirs: str,
    module_path: str = "",
    test_command: str = "",
    include_procedural: bool = True,
    model: str = ""
) -> dict:
    """Agentic hotspot analysis with optional procedural validation.

    Combines static code analysis with optional dynamic profiling to identify
    optimization candidates with reasoning.

    Args:
        source_dirs: Comma-separated source directories to analyze
        module_path: Optional specific module to focus on
        test_command: Optional test command for dynamic validation
        include_procedural: Whether to run profile_hotspots for validation
        model: Model to use (default: sonnet)

    Returns:
        dict with candidates array containing file, function, reasoning, scores
    """
    model = model or llm_config.model

    # Build user prompt
    user_prompt = f"""Analyze the following source directories for optimization candidates:

source_dirs: {source_dirs}
module_path: {module_path or 'all modules'}
test_command: {test_command or 'not provided'}

YOUR TASK:
1. Read the source files (use the file reading context)
2. Identify functions with algorithmic inefficiencies (O(n²) patterns, etc.)
3. Detect anti-patterns (redundant trig, string concat in loops, etc.)
4. Provide reasoning for each candidate

OUTPUT FORMAT - JSON only:
{{
  "candidates": [
    {{
      "file": "path/to/file.py",
      "function": "function_name",
      "line_range": [start, end],
      "static_score": 0-100,
      "complexity_class": "O(n²)",
      "patterns_found": ["nested_loop", "redundant_trig"],
      "reasoning": "Explanation of why this is slow",
      "optimization_strategies": ["Vectorize", "Precompute trig tables"],
      "optimization_potential": "high"
    }}
  ],
  "metadata": {{
    "files_analyzed": N,
    "functions_evaluated": M
  }}
}}

Output ONLY the JSON, no other text.
"""

    # Call LLM
    response = _call_llm(
        system_prompt=AGENT_PROMPTS["hotspot-scout"],
        user_prompt=user_prompt,
        model=model,
        max_tokens=8192,
    )

    # Parse response
    try:
        # Extract JSON from response
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        else:
            json_str = response

        result = json.loads(json_str.strip())
    except json.JSONDecodeError:
        result = {"error": "Failed to parse LLM response as JSON", "raw_response": response[:2000]}

    # Optionally add procedural validation
    if include_procedural and test_command:
        procedural = profile_hotspots(test_command, source_dirs, module_path, top_n=10)
        result["procedural_validation"] = procedural

    return result


@mcp.tool()
def analyze_novelty(
    candidate_code: str,
    reference_codes: str,  # JSON array of strings
    model: str = ""
) -> dict:
    """Semantic novelty analysis using LLM.

    Determines if code changes represent genuine algorithmic innovation
    vs. cosmetic rewrites.

    Args:
        candidate_code: The new/optimized code
        reference_codes: JSON array of previous approaches to compare
        model: Model to use (default: sonnet)

    Returns:
        dict with novelty_score, is_novel, similarity_breakdown, reasoning
    """
    model = model or llm_config.model

    try:
        refs = json.loads(reference_codes)
    except json.JSONDecodeError:
        refs = [reference_codes] if reference_codes else []

    user_prompt = f"""Analyze whether this candidate code is GENUINELY NOVEL compared to references.

CANDIDATE CODE:
```python
{candidate_code}
```

REFERENCE APPROACHES:
{chr(10).join(f"--- Reference {i+1} ---{chr(10)}{ref}{chr(10)}" for i, ref in enumerate(refs)) if refs else "No references (first approach)"}

YOUR TASK:
1. Analyze algorithmic similarity (same algorithm? different?)
2. Analyze data structure similarity
3. Analyze optimization technique similarity
4. Determine if this is genuinely novel or just cosmetic changes

OUTPUT FORMAT - JSON only:
{{
  "novelty_score": 0-100,
  "is_novel": true/false,
  "similarity_breakdown": {{
    "structural": 0.0-1.0,
    "algorithmic": 0.0-1.0,
    "data_structure": 0.0-1.0,
    "optimization_technique": 0.0-1.0
  }},
  "reasoning": "Explanation of why this is or isn't novel",
  "key_differences": ["list of meaningful differences"],
  "cosmetic_changes": ["list of cosmetic-only changes"]
}}

Output ONLY the JSON.
"""

    response = _call_llm(
        system_prompt=AGENT_PROMPTS["novelty-checker"],
        user_prompt=user_prompt,
        model=model,
    )

    try:
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        else:
            json_str = response
        return json.loads(json_str.strip())
    except json.JSONDecodeError:
        return {"error": "Failed to parse response", "raw": response[:1000]}


@mcp.tool()
def diagnose_failures(
    test_command: str,
    test_output: str,
    changed_files: str,  # JSON array
    model: str = ""
) -> dict:
    """Agentic test failure diagnosis.

    Analyzes test failures, categorizes them, and suggests fixes.

    Args:
        test_command: The test command that was run
        test_output: The test output (stdout/stderr)
        changed_files: JSON array of files that were modified
        model: Model to use (default: sonnet)

    Returns:
        dict with failures array, diagnosis, fix_suggestions
    """
    model = model or llm_config.model

    try:
        files = json.loads(changed_files)
    except json.JSONDecodeError:
        files = [changed_files]

    user_prompt = f"""Diagnose these test failures after optimization.

TEST COMMAND: {test_command}

CHANGED FILES:
{chr(10).join(f"- {f}" for f in files)}

TEST OUTPUT:
```
{test_output[:10000]}  # Truncate very long output
```

YOUR TASK:
1. Identify each failing test
2. Categorize the failure type
3. Determine root cause
4. Suggest specific fixes

OUTPUT FORMAT - JSON only:
{{
  "result": "FAIL",
  "failures": [
    {{
      "test": "test_name",
      "error_type": "AssertionError|IndexError|etc",
      "category": "float_precision|edge_case|logic_error|etc",
      "root_cause": "explanation",
      "fix_suggestion": {{
        "type": "adjust_tolerance|add_guard|fix_logic",
        "description": "what to do",
        "code_change": "specific code if applicable"
      }}
    }}
  ],
  "overall_diagnosis": "summary of what went wrong",
  "regression_risk": "low|medium|high"
}}

Output ONLY the JSON.
"""

    response = _call_llm(
        system_prompt=AGENT_PROMPTS["correctness-evaluator"],
        user_prompt=user_prompt,
        model=model,
        max_tokens=4096,
    )

    try:
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        else:
            json_str = response
        return json.loads(json_str.strip())
    except json.JSONDecodeError:
        return {"error": "Failed to parse response", "raw": response[:1000]}


@mcp.tool()
def analyze_timing(
    before_code: str,
    after_code: str,
    timing_result: str,  # JSON from evaluate_timing
    model: str = ""
) -> dict:
    """Explain timing improvements with breakdown.

    Args:
        before_code: Original function code
        after_code: Optimized function code
        timing_result: JSON output from evaluate_timing tool
        model: Model to use

    Returns:
        dict with breakdown of where time was saved
    """
    model = model or llm_config.model

    user_prompt = f"""Analyze the timing improvement between these two function versions.

BEFORE (original):
```python
{before_code}
```

AFTER (optimized):
```python
{after_code}
```

TIMING RESULT:
{timing_result}

YOUR TASK:
1. Explain WHERE time was saved
2. Identify which operations were eliminated
3. Note any secondary effects (cache, GC, etc.)
4. Predict scaling behavior

OUTPUT FORMAT - JSON only:
{{
  "speedup_explanation": "overall explanation",
  "breakdown": [
    {{"operation": "what changed", "saved_ms": estimate, "reason": "why faster"}}
  ],
  "secondary_effects": ["cache locality improved", "etc"],
  "scaling_prediction": {{
    "at_10x": "expected behavior",
    "bottleneck_shift": "what might become limiting"
  }},
  "remaining_opportunities": ["what could still be optimized"]
}}

Output ONLY the JSON.
"""

    response = _call_llm(
        system_prompt=AGENT_PROMPTS["timing-analyzer"],
        user_prompt=user_prompt,
        model=model,
    )

    try:
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        else:
            json_str = response
        return json.loads(json_str.strip())
    except json.JSONDecodeError:
        return {"error": "Failed to parse response", "raw": response[:1000]}


@mcp.tool()
def fuse_scout_results(
    scout_results: str,  # JSON array of scout outputs
    model: str = ""
) -> dict:
    """Combine multiple scout outputs into unified recommendations.

    Args:
        scout_results: JSON array of outputs from different scouts
        model: Model to use (default: sonnet)

    Returns:
        dict with merged, ranked candidates
    """
    model = model or llm_config.model

    user_prompt = f"""Combine these scout analysis results into unified recommendations.

SCOUT RESULTS:
{scout_results}

YOUR TASK:
1. Normalize scores from all scouts to 0-100 scale
2. Merge candidates with same (file, function)
3. Combine reasoning from all sources
4. Rank by combined score with confidence weighting
5. Resolve any conflicts between scouts

OUTPUT FORMAT - JSON only:
{{
  "candidates": [
    {{
      "file": "path",
      "function": "name",
      "combined_score": 0-100,
      "confidence": 0-1,
      "scores_by_scout": {{"static": X, "dynamic": Y, "pattern": Z}},
      "merged_reasoning": {{
        "primary_bottleneck": "...",
        "optimization_strategies": [...]
      }},
      "recommendation": "HIGH|EDIUM|LOW priority"
    }}
  ],
  "conflicts_resolved": ["description of any conflicts and how resolved"]
}}

Output ONLY the JSON.
"""

    response = _call_llm(
        system_prompt=AGENT_PROMPTS["hotspot-fusion"],
        user_prompt=user_prompt,
        model=model,
        max_tokens=8192,
    )

    try:
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        else:
            json_str = response
        return json.loads(json_str.strip())
    except json.JSONDecodeError:
        return {"error": "Failed to parse response", "raw": response[:1000]}


@mcp.tool()
def optimize_function(
    function_code: str,
    analysis: str,  # JSON from scout
    strategy: str,
    previous_attempts: str,  # JSON array of previous code
    island_id: int,
    model: str = ""
) -> dict:
    """Generate an optimized version of a function.

    Args:
        function_code: Original function to optimize
        analysis: JSON analysis of why it's slow
        strategy: Strategy hint (vectorize, memoize, etc.)
        previous_attempts: JSON array of previous optimization attempts
        island_id: Which island (affects strategy focus)
        model: Model to use (haiku for speed, sonnet for quality, opus for novel)

    Returns:
        dict with optimized_code, explanation, estimated_speedup
    """
    # Choose model based on island
    if not model:
        if island_id == 4:  # Novel algorithm island
            model = llm_config.opus_model
        else:
            model = llm_config.haiku_model

    user_prompt = f"""Generate an optimized version of this function.

ORIGINAL FUNCTION:
```python
{function_code}
```

ANALYSIS (why it's slow):
{analysis}

STRATEGY HINT: {strategy}

PREVIOUS ATTEMPTS (avoid these):
{previous_attempts if previous_attempts != "[]" else "None - this is the first attempt"}

ISLAND {island_id} FOCUS:
- Island 0: Vectorization, numpy, eliminate Python loops
- Island 1: Reduce allocations, in-place operations
- Island 2: Memoize, precompute, cache
- Island 3: Different data structures (set, deque, etc.)
- Island 4: Novel algorithm, reduce complexity class

YOUR TASK:
Generate an optimized version that:
1. Preserves EXACT behavior (same inputs → same outputs)
2. Improves performance using the strategy hint
3. Is DIFFERENT from previous attempts
4. Is valid Python code

OUTPUT FORMAT - JSON only:
{{
  "optimized_code": "the complete optimized function",
  "explanation": "what was changed and why",
  "estimated_speedup": "X-Yx",
  "risks": ["any potential issues"],
  "island": {island_id}
}}

Output ONLY the JSON.
"""

    response = _call_llm(
        system_prompt=AGENT_PROMPTS["evo-optimizer"],
        user_prompt=user_prompt,
        model=model,
        max_tokens=4096,
        temperature=0.8,  # Higher temperature for creativity
    )

    try:
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```python" in response:
            # Handle case where model outputs code directly
            code = response.split("```python")[1].split("```")[0]
            return {"optimized_code": code.strip(), "raw_response": response}
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        else:
            json_str = response
        return json.loads(json_str.strip())
    except json.JSONDecodeError:
        return {"error": "Failed to parse response", "raw": response[:2000]}


@mcp.tool()
def create_optimization_plan(
    source_dirs: str,
    test_command: str,
    max_candidates: int = 3,
    model: str = ""
) -> dict:
    """Create a complete optimization plan.

    Orchestrates scouting, fusion, and strategy planning.

    Args:
        source_dirs: Source directories to analyze
        test_command: Test command for validation
        max_candidates: Maximum candidates to include
        model: Model to use

    Returns:
        Complete plan suitable for writing to plan.yaml
    """
    model = model or llm_config.model

    # Run scouts
    procedural = profile_hotspots(test_command, source_dirs, top_n=10)
    agentic = scout_hotspots(source_dirs, "", test_command, include_procedural=False, model=model)

    # Fuse results
    fused = fuse_scout_results(json.dumps([procedural, agentic]), model=model)

    # Build plan
    candidates = fused.get("candidates", [])[:max_candidates]

    plan = {
        "metadata": {
            "created": datetime.now().isoformat(),
            "discovery_method": "hybrid",
            "total_found": len(fused.get("candidates", [])),
            "selected": len(candidates),
        },
        "config": {
            "test_command": test_command,
            "source_dirs": source_dirs,
            "max_candidates": max_candidates,
        },
        "candidates": [],
    }

    for i, cand in enumerate(candidates):
        plan["candidates"].append({
            "id": f"opt-{i+1:03d}",
            "function": cand.get("function"),
            "file": cand.get("file"),
            "status": "pending",
            "procedural": {
                "baseline_ms": cand.get("baseline_ms"),
                "time_pct": cand.get("time_pct"),
            },
            "agentic": {
                "complexity_class": cand.get("complexity_class"),
                "patterns_found": cand.get("patterns_found", []),
                "reasoning": cand.get("reasoning"),
            },
            "confidence": cand.get("confidence"),
            "strategies": cand.get("optimization_strategies", []),
        })

    return plan


# ---------------------------------------------------------------------------
# Configuration Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def set_llm_config(
    model: str = "",
    haiku_model: str = "",
    opus_model: str = "",
    max_tokens: int = 0,
    temperature: float = -1
) -> dict:
    """Update LLM configuration.

    Args:
        model: Default model for agents
        haiku_model: Fast model for simple tasks
        opus_model: Most capable model
        max_tokens: Max tokens per request
        temperature: Temperature for generation

    Returns:
        Updated config
    """
    global llm_config
    if model:
        llm_config.model = model
    if haiku_model:
        llm_config.haiku_model = haiku_model
    if opus_model:
        llm_config.opus_model = opus_model
    if max_tokens > 0:
        llm_config.max_tokens = max_tokens
    if temperature >= 0:
        llm_config.temperature = temperature
    return asdict(llm_config)


@mcp.tool()
def get_llm_config() -> dict:
    """Get current LLM configuration."""
    return asdict(llm_config)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
