# Task 2.1: Stop-Hook Evolution Integration

## Goal (from must_haves)
**Truths:**
- After a failed verification (token mismatch), evo_eval.py is called to evaluate the current iteration's attempt
- evo_db.py --add is called to store the evaluation result in the population
- On the first iteration, evo_pollinator.py --pollinate seeds the population from similar completed tasks
- The next iteration's prompt is prefixed with EVOLUTION CONTEXT from evo_prompt.py --build instead of the old LEARNINGS_PREFIX
- The population directory .planning/evolution/{task_id}/ is created on first iteration
- If evo scripts are missing or fail, the hook degrades gracefully (no crash, falls back to basic retry)

**Artifacts:**
- hooks/stop-hook.sh (modified)
- tests/bash/evo-stop-hook.bats

## Context
This is the integration point where the evolutionary intelligence system connects to the existing VGL loop. The stop-hook fires after every Claude session exit. When verification fails (token not found/mismatched), the hook currently retries with the same prompt, optionally prefixed with learnings from learnings.py.

This task replaces the learnings injection (around lines 186-228 of stop-hook.sh) with the evolution engine. After each failed iteration:
1. The attempt is evaluated (evo_eval.py captures test metrics and artifacts)
2. The result is stored in the population (evo_db.py adds to MAP-Elites grid)
3. The next prompt gets rich evolution context (evo_prompt.py builds parent + inspirations + artifacts)

The stop-hook.sh currently has two main code paths:
- **Token MATCH (line 132-320):** Verification passed -> auto-transition to next task (plan mode) or cleanup
- **Token MISMATCH (line 322-361):** Verification failed -> increment iteration, inject same prompt -> block and re-inject

The evolution integration modifies BOTH paths:
- The auto-transition path (plan mode success): replace LEARNINGS_PREFIX with EVOLUTION_PREFIX for the NEXT task
- The retry path (token mismatch): evaluate current attempt, store in population, build evolution context for retry

## Backend Deliverables
Modify `hooks/stop-hook.sh`:

### 1. After failed verification, BEFORE incrementing iteration (insert after line 327):
```bash
# --- Evolution: evaluate this iteration's attempt ---
PLUGIN_ROOT="$(dirname "$(dirname "$(realpath "$0")")")"
TASK_ID=$(echo "$FRONTMATTER" | grep '^task_id:' | sed 's/task_id: *//' | sed 's/^"\(.*\)"$/\1/' || echo "")
EVO_DB_PATH=".planning/evolution/${TASK_ID}/"
TEST_COMMAND=$(echo "$FRONTMATTER" | grep '^test_command:' | sed 's/test_command: *//' | sed 's/^"\(.*\)"$/\1/' || echo "")

# Create population dir on first iteration
if [[ ! -d "$EVO_DB_PATH" ]]; then
  mkdir -p "$EVO_DB_PATH"
fi

# Evaluate current attempt
EVO_EVAL_SCRIPT="${PLUGIN_ROOT}/scripts/evo_eval.py"
if [[ -f "$EVO_EVAL_SCRIPT" ]] && [[ -n "$TEST_COMMAND" ]]; then
  EVAL_METRICS=$(python3 "$EVO_EVAL_SCRIPT" --evaluate "$TEST_COMMAND" 2>/dev/null || echo '{}')

  # Store in population
  EVO_DB_SCRIPT="${PLUGIN_ROOT}/scripts/evo_db.py"
  if [[ -f "$EVO_DB_SCRIPT" ]] && [[ "$EVAL_METRICS" != "{}" ]]; then
    python3 "$EVO_DB_SCRIPT" --db-path "$EVO_DB_PATH" --add "$EVAL_METRICS" 2>/dev/null || true
  fi
fi
```

### 2. On first iteration only, pollinate from similar tasks:
```bash
# Pollinate on first iteration
if [[ "$ITERATION" == "1" ]] || [[ "$ITERATION" == "0" ]]; then
  EVO_POLLINATOR="${PLUGIN_ROOT}/scripts/evo_pollinator.py"
  PLAN_FILE=".claude/plan/plan.yaml"
  if [[ -f "$EVO_POLLINATOR" ]] && [[ -f "$PLAN_FILE" ]] && [[ -n "$TASK_ID" ]]; then
    python3 "$EVO_POLLINATOR" --pollinate "$EVO_DB_PATH" "$PLAN_FILE" "$TASK_ID" 2>/dev/null || true
  fi
fi
```

### 3. Replace LEARNINGS_PREFIX with EVOLUTION_PREFIX when building next prompt:
Replace the existing LEARNINGS_PREFIX block (lines ~186-228) with:
```bash
# Build evolution context for next iteration (replaces LEARNINGS_PREFIX)
EVOLUTION_PREFIX=""
EVO_PROMPT_SCRIPT="${PLUGIN_ROOT}/scripts/evo_prompt.py"
if [[ -f "$EVO_PROMPT_SCRIPT" ]] && [[ -d "$EVO_DB_PATH" ]] && [[ -n "$TASK_ID" ]]; then
  EVO_CONTEXT=$(python3 "$EVO_PROMPT_SCRIPT" --build "$EVO_DB_PATH" "$TASK_ID" 2>/dev/null || echo "")
  if [[ -n "$EVO_CONTEXT" ]]; then
    EVOLUTION_PREFIX="EVOLUTION CONTEXT:
${EVO_CONTEXT}

"
  fi
fi
```

Then update the prompt assembly line (currently line 230) from:
```bash
NEXT_TASK_PROMPT="${LEARNINGS_PREFIX}${INTEGRATION_PREFIX}CRITICAL RULES..."
```
to:
```bash
NEXT_TASK_PROMPT="${EVOLUTION_PREFIX}${INTEGRATION_PREFIX}CRITICAL RULES..."
```

### 4. Graceful degradation:
- Every evo script call is wrapped in `|| true` or `|| echo '{}'`
- Missing scripts: detected via `[[ -f "$SCRIPT" ]]` before calling
- Failed evo_db.py: logged via debug(), continues without evolution context
- Failed evo_prompt.py: EVOLUTION_PREFIX remains empty, prompt sent without context

### Code to remove:
- The LEARNINGS_PREFIX block (lines ~186-228 in current stop-hook.sh): replace entirely with EVOLUTION_PREFIX
- References to `learnings.py` and `LEARNINGS_STORAGE` variables

## Frontend Deliverables
- System message includes evolution context indicator: "VGL iteration N | Evolution-guided"
- stderr logging shows evolution actions: "VGL: Evaluating iteration attempt", "VGL: Stored in population", "VGL: Pollinating from similar tasks"

## Tests to Write (TDD-First)

### tests/bash/evo-stop-hook.bats
- test_evo_eval_called_on_failure -- set up state file with task_id + token mismatch, verify evo_eval.py invoked (mock script logs its call to a tracking file)
- test_evo_db_add_called -- verify evo_db.py --add called with metrics JSON after evaluation
- test_evolution_context_injected -- verify next prompt output JSON contains "EVOLUTION CONTEXT" in the reason field
- test_first_iteration_pollination -- set iteration=1 in state file, verify evo_pollinator.py --pollinate called (mock logs invocation)
- test_graceful_without_evo_scripts -- remove evo scripts from mock path, verify hook still produces valid block JSON output without crash
- test_population_dir_created -- verify .planning/evolution/{task_id}/ directory created on first hook invocation
- test_empty_population_works -- first iteration with no prior population data succeeds and produces valid JSON prompt output
- test_population_persists -- run hook twice simulating two failed iterations, verify population directory has data after second run

## Test Dependency Graph

| Test | File | Depends On | Guidance |
|------|------|-----------|----------|
| T1 | tests/bash/evo-stop-hook.bats | -- | Modify hooks/stop-hook.sh to replace LEARNINGS_PREFIX with EVOLUTION_PREFIX and add evo_eval/evo_db calls on failure path. Create mock evo scripts (evo_eval.py, evo_db.py, evo_prompt.py, evo_pollinator.py) that echo expected JSON and log their invocations to a temp tracking file. Set up bats fixture with: state file (verifier-loop.local.md with frontmatter including task_id and test_command), token file (verifier-token.secret with VGL_COMPLETE_ token), transcript file (without matching token to trigger mismatch). Test by piping hook input JSON (with transcript_path) to stop-hook.sh and checking output JSON structure + side effects in tracking file. Follow pattern from existing tests/bash/stop-hook.bats. |

Dispatch order:
- Wave 1: T1

## Key Links
- Integration target: hooks/stop-hook.sh (current VGL loop)
- Token MATCH path: lines 132-320 (auto-transition, LEARNINGS_PREFIX for next task)
- Token MISMATCH path: lines 322-361 (retry with same prompt)
- Depends on: scripts/evo_eval.py (task 1.2), scripts/evo_db.py (task 1.1), scripts/evo_prompt.py (task 1.3), scripts/evo_pollinator.py (task 2.3)
- Current learnings injection: hooks/stop-hook.sh lines 186-228 (LEARNINGS_PREFIX block)
- Existing test pattern: tests/bash/stop-hook.bats

## Technical Notes
- The stop-hook receives JSON on stdin: `{"transcript_path": "/path/to/transcript.jsonl"}`
- The hook must output valid JSON: `{"decision": "block", "reason": "...", "systemMessage": "..."}`
- All evo script calls must be non-blocking and fail-safe (2>/dev/null || true)
- The task_id is extracted from state file frontmatter -- ensure it is present in the YAML
- test_command is also from frontmatter -- needed by evo_eval.py to know what tests to run
- Population path uses task_id which may contain dots (e.g., "1.1") -- this is safe for filesystem paths
- The LEARNINGS_PREFIX replacement happens in TWO places in stop-hook.sh:
  1. The auto-transition path (plan_mode success, around line 230) -- for the NEXT task's prompt
  2. The retry path (token mismatch, around line 328) -- for the current task's retry prompt
  Both must be updated to use EVOLUTION_PREFIX
