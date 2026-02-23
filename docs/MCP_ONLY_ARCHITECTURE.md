# MCP-Only Architecture

## Overview

Move ALL token generation (LLM calls) through MCP server tools. Commands no longer spawn Task agents directly - they only call MCP tools.

## Current vs Proposed

### Current (Mixed)
```
Command
├── mcp__tool_call()        ← MCP tools
└── Task(subagent=...)      ← Direct agent spawning
```

### Proposed (MCP-Only)
```
Command
└── mcp__tool_call()        ← All operations through MCP
    └── MCP Server
        ├── Procedural tools (scripts)
        └── Agentic tools (LLM calls)
```

## Benefits

1. **Centralized Control** - MCP server manages all LLM interactions
2. **Consistent Interface** - Everything is a tool call
3. **Easier Logging** - All operations logged in one place
4. **Backend Flexibility** - Can swap Claude for OpenAI, local models, etc.
5. **State Management** - MCP can track session state
6. **Cost Tracking** - Central token counting
7. **Retry Logic** - MCP handles retries uniformly

## Tool Categories

### v1 Procedural Tools (Preserved)
| Tool | Purpose |
|------|---------|
| `profile_hotspots` | cProfile analysis |
| `population_sample/add/best/stats/migrate` | MAP-Elites DB |
| `evaluate_correctness/timing` | Test validation |
| `extract/replace/revert_function` | Code manipulation |
| `check_novelty` | Structural diff |

### v2 Agentic Tools (New)
| Tool | Purpose | LLM Usage |
|------|---------|-----------|
| `scout_hotspots` | Agentic code analysis | Claude call |
| `analyze_novelty` | Semantic novelty check | Claude call |
| `diagnose_failures` | Test failure diagnosis | Claude call |
| `analyze_timing` | Timing breakdown | Claude call |
| `fuse_scout_results` | Merge scout outputs | Claude call |
| `optimize_function` | Generate optimized code | Claude call |
| `create_optimization_plan` | Full planning workflow | Multiple Claude calls |

## Example: Hyperphase Command (MCP-Only)

### Before (with Task spawning)
```
Phase S1:
  Task(subagent='gatekeeper:evo-scout', ...)
  Task(subagent='gatekeeper:hotspot-scout', ...)

Phase S2:
  Task(subagent='gatekeeper:evo-optimizer', ...)  ×5 islands
```

### After (MCP-only)
```
Phase P1:
  mcp__scout_hotspots(include_procedural=true)

Phase E2:
  mcp__optimize_function(island_id=0, strategy="vectorize")
  mcp__optimize_function(island_id=1, strategy="reduce_allocations")
  ...
```

## Command Rewrite: hyperphase-mcp.md

```markdown
---
description: "Hyperphase N via MCP - All operations through MCP tools, no Task spawning"
---

## Phase P1 — Discovery (MCP Only)

# Procedural + Agentic in single call
result = mcp__plugin_gatekeeper_evolve-mcp__scout_hotspots(
    source_dirs="{source_dirs}",
    test_command="{test_command}",
    include_procedural=True
)

## Phase P2 — Optimization (MCP Only)

for island in range(5):
    opt = mcp__plugin_gatekeeper_evolve-mcp__optimize_function(
        function_code=extracted_function,
        analysis=candidate_analysis,
        strategy=ISLAND_STRATEGIES[island],
        previous_attempts=json.dumps(previous_codes),
        island_id=island
    )

    mcp__plugin_gatekeeper_evolve-mcp__population_add(
        db_path=db_path,
        approach_json=json.dumps(opt)
    )
```

## Backend Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Command Layer                               │
│   hyperphase-mcp.md - Only MCP tool calls, no Task()               │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ MCP Protocol
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Evolve-MCP Server v2                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                  Procedural Tools                            │   │
│  │  profile_hotspots, population_*, evaluate_*, *_function      │   │
│  │                                                              │   │
│  │  → Subprocess → Python scripts                              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                  Agentic Tools                               │   │
│  │  scout_*, analyze_*, diagnose_*, fuse_*, optimize_*         │   │
│  │                                                              │   │
│  │  → LLM Backend → anthropic.messages.create()                │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                  LLM Backend                                 │   │
│  │                                                              │   │
│  │  config: {model, max_tokens, temperature}                   │   │
│  │  client: anthropic.Anthropic()                              │   │
│  │                                                              │   │
│  │  Future: OpenAI, local models, etc.                         │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Token Tracking (MCP-managed)

```python
# In MCP server
class TokenTracker:
    def __init__(self):
        self.total_input = 0
        self.total_output = 0
        self.by_tool = {}

    def record(self, tool_name, input_tokens, output_tokens):
        self.total_input += input_tokens
        self.total_output += output_tokens
        self.by_tool[tool_name] = self.by_tool.get(tool_name, {"in": 0, "out": 0})
        self.by_tool[tool_name]["in"] += input_tokens
        self.by_tool[tool_name]["out"] += output_tokens

@mcp.tool()
def get_token_usage() -> dict:
    """Get token usage statistics."""
    return {
        "total_input": tracker.total_input,
        "total_output": tracker.total_output,
        "by_tool": tracker.by_tool,
        "estimated_cost": compute_cost(tracker),
    }
```

## Retry Logic (MCP-managed)

```python
def _call_llm_with_retry(prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            return client.messages.create(...)
        except anthropic.RateLimitError:
            time.sleep(2 ** attempt)  # Exponential backoff
        except anthropic.APIError as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(1)
```

## Model Selection

```python
# Per-tool model selection
MODEL_DEFAULTS = {
    "scout_hotspots": "sonnet",      # Needs understanding
    "analyze_novelty": "sonnet",     # Needs reasoning
    "optimize_function": "haiku",    # Speed > quality for most islands
    "optimize_function_island_4": "opus",  # Novel algorithms need best model
}

@mcp.tool()
def optimize_function(..., island_id: int, model: str = ""):
    if not model:
        if island_id == 4:
            model = "claude-opus-4-20250514"
        else:
            model = "claude-haiku-3-5-20241022"
```

## Session State (MCP-managed)

```python
# MCP can maintain state across calls
session_state = {
    "plans_created": [],
    "optimizations_run": 0,
    "functions_modified": [],
    "rollbacks": [],
}

@mcp.tool()
def get_session_state() -> dict:
    """Get current session state."""
    return session_state
```

## Migration Path

1. **Phase 1**: Keep both Task spawning and MCP tools
2. **Phase 2**: Commands use MCP tools, but Task spawning still available
3. **Phase 3**: Remove Task spawning from commands, MCP-only

## Files

| File | Purpose |
|------|---------|
| `evolve-mcp/server_v2.py` | MCP server with agentic tools |
| `commands/hyperphase-mcp.md` | MCP-only hyperphase command |
| `docs/MCP_ONLY_ARCHITECTURE.md` | This document |
