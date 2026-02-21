#!/usr/bin/env python3
"""Quibbler BS Detector — in-flight agent quality gate.

Monitors gatekeeper subagent sessions (tester, assessor, executor) by reading
their full chat transcript at random intervals during execution.

Subcommands:
  check   — PostToolUse handler: tracks steps per session, reads full
             transcript at random intervals (3-8 steps), calls haiku via
             proxy with the chat log + task.md, writes feedback if issues found.
  notify  — PreToolUse handler: reads feedback file, prints to stderr,
             deletes file.
"""

import json
import os
import random
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROXY_URL = "http://127.0.0.1:3457/v1/messages"
MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1024
QUIBBLER_DIR = ".quibbler"
SESSIONS_DIR = os.path.join(QUIBBLER_DIR, "sessions")
DEBUG_LOG = "/tmp/quibbler-bs.debug.log"

MIN_STEPS = 3
MAX_STEPS = 8
MAX_RETRIES = 2  # retries if response contains banned phrases

# Phrases that indicate the quibbler itself is being vague/lazy
BANNED_PHRASES = re.compile(
    r"graceful(?:ly)?\s+(?:fallback|degrad|fail|handl)",
    re.I,
)

# Regex to extract the Sanctioned Mocks section from a task.md
SANCTIONED_MOCKS_RE = re.compile(
    r"## Sanctioned Mocks & Stubs\n(.*?)(?=\n## |\Z)",
    re.DOTALL,
)

# Agent type detection: patterns found in early transcript lines
# Maps regex -> agent type
AGENT_DETECTION = [
    (re.compile(r"Gatekeeper test architect|TESTS_WRITTEN|tester agent", re.I),
     "gatekeeper:tester"),
    (re.compile(r"test quality assessor|ASSESSMENT_PASS|ASSESSMENT_FAIL", re.I),
     "gatekeeper:assessor"),
    (re.compile(r"Gatekeeper task executor|IMPLEMENTATION_READY|executor agent", re.I),
     "gatekeeper:executor"),
]

# Task ID pattern: "task-1.2" or "Task 1.2" etc.
TASK_ID_RE = re.compile(r"task[- _](\d+\.\d+)", re.I)

# ---------------------------------------------------------------------------
# Agent-specific BS detection prompts
# ---------------------------------------------------------------------------

# Shared preamble injected into all agent prompts
_SHARED_PREAMBLE = """\
You are given the full dependency graph context: the assigned task.md, all \
upstream task specs (tasks this one depends on), all downstream task specs \
(tasks that depend on this one), and phase-level must_haves.

NAMING & ATTRIBUTE CONFORMANCE (check this on EVERY review):
Cross-reference the agent's work against the plan specs. Flag ANY mismatch:
- File paths: does the agent use the exact paths from the task spec? \
(e.g., task says `scripts/evo_db.py` but agent writes `src/evo_db.py`)
- Function/method names: do they match what the spec defines? \
(e.g., task says `EvolutionDB.sample()` but agent writes `EvolutionDB.get_sample()`)
- Class names: exact match required against spec
- Variable/field names: dataclass fields, config keys, CLI flags must match spec exactly
- Test file paths: must match the artifact paths in the task spec
- Import paths: must be consistent with where files are actually placed
- CLI interface: flags, arguments, output format must match spec
If the spec says `--db-path`, the code must not use `--database-path`. \
If the spec says `Approach.prompt_addendum`, the code must not use `Approach.addendum`. \
Names are a contract — deviations break downstream tasks.

SANCTIONED MOCKS & STUBS:
The task spec may include a "Sanctioned Mocks & Stubs" section — an explicit \
allowlist of mocks/stubs that are permitted for this task. You will receive this \
list in the context under "=== SANCTIONED MOCKS & STUBS ===".
- If a mock/stub IS on the sanctioned list: it is allowed — do not flag it.
- If a mock/stub is NOT on the sanctioned list: flag it as UNSANCTIONED MOCK.
- If the section says "None": ANY mock or stub is a violation.
- If the section is missing from the task spec: treat all mocks as suspicious \
and flag with a note that the task spec should define sanctioned mocks.

HARD NOs — these are absolute violations, always flag:
- Renaming anything defined in the task spec without explicit justification
- Using different file paths than what the spec declares
- Changing the public API surface (function signatures, CLI flags, output format) \
from what the spec defines
- Inventing new abstractions not in the spec that downstream tasks won't expect
- Silently swallowing errors (catch-all except: pass)
- Using mocks/stubs not on the sanctioned list

"""

_SHARED_RESPONSE_FORMAT = """
Respond with ONLY one of these two formats:

If issues found:
ISSUES FOUND
1. [Category]: Description of the specific problem
2. [Category]: ...

If output looks solid so far:
APPROVED

CRITICAL: Your response must be actionable and specific. Do NOT use the phrase \
"graceful fallback" or "gracefully degrades" or any variation — say exactly what \
should happen on failure (raise, return empty, log and skip, etc)."""

TESTER_BS_PROMPT = _SHARED_PREAMBLE + """\
You are reviewing the LIVE transcript of a TEST-WRITING agent. \
You can see everything the agent has done so far — every tool call, every file \
read, every file written. Your job is to catch low-quality work in progress.

Watch for these specific anti-patterns:

1. TRIVIAL/TOY TEST DATA: Tests using "foo", "bar", "test", "123", "hello \
world" instead of realistic domain data. Real tests need realistic inputs.

2. OVER-MOCKING / UNSANCTIONED MOCKS: Check every mock against the sanctioned \
mocks list. If a mock is not on the list, flag it. Mocking the system under test \
itself always defeats the purpose regardless of the allowlist.

3. ALWAYS-PASSING TESTS: Trivial assertions like `expect(true).toBe(true)`, \
`assert 1 == 1`, empty test bodies, or tests that can never fail regardless of \
the implementation.

4. MISSING EDGE CASES: Only happy-path tests with no error paths, boundary \
conditions, empty inputs, or invalid data scenarios.

5. MUST_HAVES MISALIGNMENT: Tests that don't cover the must_haves from the \
task specification. Every must_have should have corresponding test coverage.

6. IMPLEMENTATION-DETAIL TESTING: Tests that assert on internal state, private \
methods, or specific implementation choices rather than observable behavior.

7. NAMING DRIFT: Test files, test function names, or tested API surfaces that \
don't match the names defined in the task spec or upstream/downstream task specs.
""" + _SHARED_RESPONSE_FORMAT

ASSESSOR_BS_PROMPT = _SHARED_PREAMBLE + """\
You are reviewing the LIVE transcript of an ASSESSOR agent \
(quality evaluator). You can see everything the agent has done so far — every \
file it read, every analysis step. Your job is to catch rubber-stamping and \
superficial reviews in progress.

Watch for these specific anti-patterns:

1. RUBBER-STAMP PASS: Issuing ASSESSMENT_PASS without substantive analysis. \
A real assessment must reference specific files, specific tests, and specific \
quality dimensions.

2. MISSING QUALITY DIMENSIONS: Only checking one aspect (e.g., "tests pass") \
without examining test quality, coverage of must_haves, edge cases, error \
handling, and alignment with task spec.

3. IGNORING MUST_HAVES: Not checking whether the tests actually cover each \
must_have item from the task specification. The assessor must enumerate \
must_haves and verify each one.

4. NOT READING FILES: Claiming to have reviewed tests without showing evidence \
of actually reading the test files (no file paths, no line references, no \
specific assertions mentioned).

5. SUPERFICIAL CHECK: Generic praise like "tests look good" or "comprehensive \
coverage" without pointing to specific tests or specific scenarios that \
demonstrate this.

6. NAMING CONFORMANCE SKIP: Not verifying that test file paths, function names, \
class names, and CLI interfaces match what the task spec defines.
""" + _SHARED_RESPONSE_FORMAT

EXECUTOR_BS_PROMPT = _SHARED_PREAMBLE + """\
You are reviewing the LIVE transcript of an EXECUTOR agent \
(code implementer). You can see everything the agent has done so far — every \
file read, every file written, every command run. Your job is to catch \
hallucinated implementations and shortcuts in progress.

Watch for these specific anti-patterns:

1. HALLUCINATED IMPLEMENTATION: Claiming things work without evidence of \
actually running tests. Look for "should work", "this will", "tests would \
pass" language instead of actual test output.

2. MODIFIED TESTER-WRITTEN TESTS: The executor is FORBIDDEN from modifying \
tests written by the tester. Any mention of changing, updating, fixing, or \
"adjusting" test files is a violation.

3. SKIPPED DEPENDENCY ORDER: Not following the test dependency graph. Tests \
should be made to pass in dependency order, not all at once or in random order.

4. CORNER-CUTTING / UNSANCTIONED STUBS: Hardcoded return values, TODO/FIXME \
placeholders, stub implementations, empty function bodies, or "will implement \
later" patterns. Check stubs against the sanctioned mocks list — only stubs \
explicitly sanctioned in the task spec are permitted.

5. NOT RUNNING TESTS: No evidence of actually executing the test command. \
The executor must run tests and show real output.

6. MUST_HAVES DEVIATION: Deviating from must_haves without explicit \
justification. The implementation must satisfy every must_have.

7. NAMING/PATH VIOLATIONS: Using different file paths, class names, function \
names, CLI flags, or field names than what the task spec defines. The spec is \
the contract — downstream tasks depend on these exact names.
""" + _SHARED_RESPONSE_FORMAT

AGENT_PROMPTS = {
    "gatekeeper:tester": TESTER_BS_PROMPT,
    "gatekeeper:assessor": ASSESSOR_BS_PROMPT,
    "gatekeeper:executor": EXECUTOR_BS_PROMPT,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def debug(msg: str) -> None:
    try:
        with open(DEBUG_LOG, "a") as f:
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            f.write(f"[{ts}] {msg}\n")
    except OSError:
        pass


def call_proxy(system_prompt: str, user_content: str) -> str | None:
    """Call the model proxy and return the text response, or None on error."""
    body = json.dumps({
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_content}],
    }).encode()

    req = urllib.request.Request(
        PROXY_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key": "proxy-passthrough",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            for block in data.get("content", []):
                if block.get("type") == "text":
                    return block["text"]
    except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError) as exc:
        debug(f"Proxy call failed: {exc}")
    return None


def truncate(text: str, max_chars: int = 12000) -> str:
    """Truncate text keeping head and tail."""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n\n[...truncated...]\n\n" + text[-half:]


# ---------------------------------------------------------------------------
# Session state management
# ---------------------------------------------------------------------------

def _state_path(session_id: str) -> str:
    return os.path.join(SESSIONS_DIR, f"{session_id}.json")


def load_session_state(session_id: str) -> dict:
    """Load session state or return empty dict."""
    path = _state_path(session_id)
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_session_state(session_id: str, state: dict) -> None:
    """Persist session state."""
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    path = _state_path(session_id)
    with open(path, "w") as f:
        json.dump(state, f)


# ---------------------------------------------------------------------------
# Transcript reading and agent detection
# ---------------------------------------------------------------------------

def read_transcript_raw(transcript_path: str) -> str:
    """Read the raw transcript file content."""
    try:
        with open(transcript_path) as f:
            return f.read()
    except OSError:
        return ""


def format_transcript(transcript_path: str) -> str:
    """Read transcript JSONL and format as a readable chat log.

    Each JSONL line is parsed and formatted as:
      [role] content (truncated tool results)
    """
    lines = []
    try:
        with open(transcript_path) as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    entry = json.loads(raw_line)
                except json.JSONDecodeError:
                    # Some transcript lines may be plain text
                    lines.append(raw_line)
                    continue

                role = entry.get("role", entry.get("type", "?"))
                content = entry.get("content", "")

                # Content can be a list of blocks (Anthropic format)
                if isinstance(content, list):
                    parts = []
                    for block in content:
                        if isinstance(block, str):
                            parts.append(block)
                        elif isinstance(block, dict):
                            btype = block.get("type", "")
                            if btype == "text":
                                parts.append(block.get("text", ""))
                            elif btype == "tool_use":
                                name = block.get("name", "?")
                                inp = block.get("input", {})
                                # Show tool name + abbreviated input
                                inp_str = json.dumps(inp)
                                if len(inp_str) > 300:
                                    inp_str = inp_str[:300] + "..."
                                parts.append(f"[tool:{name}] {inp_str}")
                            elif btype == "tool_result":
                                result = str(block.get("content", block.get("output", "")))
                                if len(result) > 500:
                                    result = result[:500] + "..."
                                parts.append(f"[result] {result}")
                            else:
                                parts.append(str(block))
                    content = "\n".join(parts)
                elif isinstance(content, dict):
                    content = json.dumps(content)

                if isinstance(content, str) and len(content) > 2000:
                    content = content[:1000] + "\n[...]\n" + content[-1000:]

                lines.append(f"[{role}] {content}")
    except OSError:
        return ""

    return "\n\n".join(lines)


def detect_agent_type(transcript_path: str) -> str | None:
    """Detect the gatekeeper agent type from early transcript content."""
    # Read first 20KB — agent type markers appear in system prompt / first message
    try:
        with open(transcript_path) as f:
            head = f.read(20_000)
    except OSError:
        return None

    for pattern, agent_type in AGENT_DETECTION:
        if pattern.search(head):
            debug(f"detect: matched {agent_type}")
            return agent_type

    return None


def _extract_task_id(transcript_path: str) -> str | None:
    """Extract the task ID (e.g. '2.1') from transcript content."""
    try:
        with open(transcript_path) as f:
            head = f.read(30_000)
    except OSError:
        return None

    match = TASK_ID_RE.search(head)
    return match.group(1) if match else None


def _load_plan() -> dict | None:
    """Load and parse plan.yaml. Returns the plan dict or None."""
    plan_path = Path(".claude/plan/plan.yaml")
    if not plan_path.is_file():
        return None
    try:
        import yaml
        return yaml.safe_load(plan_path.read_text())
    except ImportError:
        debug("_load_plan: no yaml module")
        return None
    except OSError:
        return None


def _build_task_index(plan: dict) -> dict:
    """Build a flat index of task_id -> task dict from plan.yaml.

    Each entry gets an extra '_phase' key with the parent phase dict.
    """
    index = {}
    for phase in plan.get("phases", []):
        for task in phase.get("tasks", []):
            tid = str(task.get("id", ""))
            task["_phase"] = phase
            index[tid] = task
    return index


def _walk_upstream(task_id: str, index: dict) -> list[str]:
    """Walk the dependency graph upstream (transitive depends_on).

    Returns task IDs in topological order (deepest dependencies first).
    """
    visited = set()
    order = []

    def dfs(tid: str) -> None:
        if tid in visited or tid not in index:
            return
        visited.add(tid)
        for dep in index[tid].get("depends_on", []):
            dfs(str(dep))
        order.append(tid)

    for dep in index.get(task_id, {}).get("depends_on", []):
        dfs(str(dep))
    return order


def _walk_downstream(task_id: str, index: dict) -> list[str]:
    """Find all tasks that depend on task_id (direct and transitive).

    Returns task IDs in dependency order (direct dependents first).
    """
    # Build reverse adjacency: task -> list of tasks that depend on it
    reverse = {}
    for tid, task in index.items():
        for dep in task.get("depends_on", []):
            reverse.setdefault(str(dep), []).append(tid)

    visited = set()
    order = []

    def bfs(start: str) -> None:
        queue = reverse.get(start, [])
        for tid in queue:
            if tid not in visited:
                visited.add(tid)
                order.append(tid)
                bfs(tid)

    bfs(task_id)
    return order


def _format_phase_summary(phase: dict) -> str:
    """Format a phase dict into a readable summary."""
    pid = phase.get("id", "?")
    lines = [f"Phase {pid}: {phase.get('name', '')}"]
    lines.append(f"Goal: {phase.get('goal', '')}")

    mh = phase.get("must_haves", {})
    if mh.get("truths"):
        lines.append("Must-Have Truths:")
        for t in mh["truths"]:
            lines.append(f"  - {t}")
    if mh.get("artifacts"):
        lines.append("Must-Have Artifacts:")
        for a in mh["artifacts"]:
            lines.append(f"  - {a}")
    if mh.get("key_links"):
        lines.append("Key Links:")
        for k in mh["key_links"]:
            lines.append(f"  - {k}")

    for task in phase.get("tasks", []):
        tid = task.get("id", "?")
        tname = task.get("name", "?")
        tstatus = task.get("status", "?")
        deps = task.get("depends_on", [])
        dep_str = f" (depends on: {', '.join(str(d) for d in deps)})" if deps else ""
        lines.append(f"  Task {tid}: {tname} [{tstatus}]{dep_str}")

    return "\n".join(lines)


def _read_task_md(task_id: str) -> str:
    """Read .claude/plan/tasks/task-{id}.md, return content or empty string."""
    p = Path(f".claude/plan/tasks/task-{task_id}.md")
    try:
        return p.read_text() if p.is_file() else ""
    except OSError:
        return ""


def _extract_sanctioned_mocks(task_md_content: str) -> str:
    """Extract the Sanctioned Mocks & Stubs section from task.md content.

    Returns the section content, or "No sanctioned mocks section found" if absent.
    """
    match = SANCTIONED_MOCKS_RE.search(task_md_content)
    if not match:
        return "No sanctioned mocks section found — all mocks are suspect."
    section = match.group(1).strip()
    if not section or section.lower().startswith("none"):
        return "None — all code must use real implementations. Any mock is a violation."
    return section


def _format_task_summary(task: dict) -> str:
    """Format a plan.yaml task entry as a one-line summary."""
    tid = task.get("id", "?")
    name = task.get("name", "?")
    status = task.get("status", "?")
    deps = task.get("depends_on", [])
    dep_str = f" depends on [{', '.join(str(d) for d in deps)}]" if deps else ""
    return f"task-{tid}: {name} [{status}]{dep_str}"


def gather_phase_context(transcript_path: str) -> dict:
    """Gather full dependency-graph context for the current task.

    Walks plan.yaml to find:
    - The current task's .md spec
    - All upstream dependencies (transitive depends_on) with their .md files
    - All downstream dependents (tasks that depend on this one) with their .md files
    - Phase-level summaries for all involved phases

    Returns dict with keys:
      task_id:          str  — e.g. '2.1'
      current_task:     str  — content of the assigned task-{id}.md
      sanctioned_mocks: str  — allowed mocks/stubs from the task spec
      upstream_tasks:   str  — .md content of all tasks this one depends on
      downstream_tasks: str  — .md content of all tasks that depend on this one
      phase_summary:    str  — phase overview(s) for involved phases
      dep_graph:        str  — human-readable dependency flow diagram
    """
    result = {
        "task_id": "", "current_task": "", "sanctioned_mocks": "",
        "upstream_tasks": "", "downstream_tasks": "", "phase_summary": "",
        "dep_graph": "",
    }

    task_id = _extract_task_id(transcript_path)
    if not task_id:
        debug("gather: no task ID found")
        return result
    result["task_id"] = task_id

    # Read current task .md
    result["current_task"] = _read_task_md(task_id)

    # Extract sanctioned mocks from current task
    result["sanctioned_mocks"] = _extract_sanctioned_mocks(result["current_task"])
    debug(f"gather: sanctioned_mocks={result['sanctioned_mocks'][:80]}")

    # Load plan and build dependency graph
    plan = _load_plan()
    if not plan:
        debug("gather: could not load plan.yaml")
        return result

    index = _build_task_index(plan)
    if task_id not in index:
        debug(f"gather: task {task_id} not found in plan")
        return result

    current_task_entry = index[task_id]
    current_phase = current_task_entry.get("_phase", {})

    # Walk upstream (all tasks this one depends on, transitively)
    upstream_ids = _walk_upstream(task_id, index)
    upstream_parts = []
    for uid in upstream_ids:
        entry = index.get(uid, {})
        summary = _format_task_summary(entry)
        md = _read_task_md(uid)
        if md:
            upstream_parts.append(f"--- {summary} ---\n{md}")
        else:
            upstream_parts.append(f"--- {summary} ---\n(no .md file)")
        debug(f"gather: upstream {uid}")
    result["upstream_tasks"] = "\n\n".join(upstream_parts)

    # Walk downstream (all tasks that depend on this one, transitively)
    downstream_ids = _walk_downstream(task_id, index)
    downstream_parts = []
    for did in downstream_ids:
        entry = index.get(did, {})
        summary = _format_task_summary(entry)
        md = _read_task_md(did)
        if md:
            downstream_parts.append(f"--- {summary} ---\n{md}")
        else:
            downstream_parts.append(f"--- {summary} ---\n(no .md file)")
        debug(f"gather: downstream {did}")
    result["downstream_tasks"] = "\n\n".join(downstream_parts)

    # Phase summary — include current phase and any other phases touched
    involved_phases = set()
    involved_phases.add(str(current_phase.get("id", "")))
    for tid in upstream_ids + downstream_ids:
        phase = index.get(tid, {}).get("_phase", {})
        involved_phases.add(str(phase.get("id", "")))

    phase_summaries = []
    for phase in plan.get("phases", []):
        if str(phase.get("id", "")) in involved_phases:
            phase_summaries.append(_format_phase_summary(phase))
    result["phase_summary"] = "\n\n".join(phase_summaries)

    # Build a human-readable dependency flow diagram
    dep_lines = []
    if upstream_ids:
        dep_lines.append(
            "UPSTREAM (this task depends on): "
            + " -> ".join(upstream_ids) + f" -> [{task_id}]"
        )
    if downstream_ids:
        dep_lines.append(
            f"DOWNSTREAM (depend on this task): [{task_id}] -> "
            + " -> ".join(downstream_ids)
        )
    if not upstream_ids and not downstream_ids:
        dep_lines.append(f"[{task_id}] has no dependencies")
    result["dep_graph"] = "\n".join(dep_lines)

    debug(f"gather: task={task_id} upstream={len(upstream_ids)} "
          f"downstream={len(downstream_ids)} phases={len(phase_summaries)}")
    return result


# ---------------------------------------------------------------------------
# check — PostToolUse handler
# ---------------------------------------------------------------------------

def cmd_check() -> None:
    """Track steps per session, activate BS check at random intervals."""
    raw = sys.stdin.read()

    try:
        hook = json.loads(raw)
    except json.JSONDecodeError:
        return

    session_id = hook.get("session_id", "")
    transcript_path = hook.get("transcript_path", "")

    if not session_id or not transcript_path:
        return

    # Load session state
    state = load_session_state(session_id)

    # Fast exit: session already marked as non-watched
    if state.get("ignored"):
        return

    # First call in this session — detect agent type
    if "agent_type" not in state:
        agent_type = detect_agent_type(transcript_path)
        if agent_type is None:
            state["ignored"] = True
            save_session_state(session_id, state)
            return

        state["agent_type"] = agent_type
        state["step"] = 0
        state["next_activation"] = random.randint(MIN_STEPS, MAX_STEPS)
        ctx = gather_phase_context(transcript_path)
        state["task_id"] = ctx["task_id"]
        state["current_task"] = ctx["current_task"]
        state["sanctioned_mocks"] = ctx["sanctioned_mocks"]
        state["upstream_tasks"] = ctx["upstream_tasks"]
        state["downstream_tasks"] = ctx["downstream_tasks"]
        state["phase_summary"] = ctx["phase_summary"]
        state["dep_graph"] = ctx["dep_graph"]
        debug(f"check: new session {session_id} agent={agent_type} "
              f"task={ctx['task_id']} next_activation={state['next_activation']}")

    # Increment step
    state["step"] = state.get("step", 0) + 1
    step = state["step"]
    next_act = state.get("next_activation", MAX_STEPS)

    # Not time yet — save and exit
    if step < next_act:
        save_session_state(session_id, state)
        return

    # --- Activation: time for a BS check ---
    debug(f"check: ACTIVATING at step {step} for {state['agent_type']} "
          f"session={session_id}")

    # Schedule next activation
    state["next_activation"] = step + random.randint(MIN_STEPS, MAX_STEPS)
    save_session_state(session_id, state)

    agent_type = state["agent_type"]

    # Read full transcript as formatted chat log
    chat_log = format_transcript(transcript_path)
    if not chat_log:
        debug("check: empty transcript, skipping")
        return

    # Build the user message with full dependency-graph context
    parts = [f"Agent type: {agent_type}\nStep: {step}"]

    dep_graph = state.get("dep_graph", "")
    if dep_graph:
        parts.append(f"=== DEPENDENCY FLOW ===\n{dep_graph}")

    phase_summary = state.get("phase_summary", "")
    if phase_summary:
        parts.append(f"=== PHASE OVERVIEW ===\n{truncate(phase_summary, 2000)}")

    current_task = state.get("current_task", "")
    if current_task:
        parts.append(
            f"=== ASSIGNED TASK SPEC (task-{state.get('task_id', '?')}) ===\n"
            f"{truncate(current_task, 4000)}"
        )

    sanctioned = state.get("sanctioned_mocks", "")
    if sanctioned:
        parts.append(f"=== SANCTIONED MOCKS & STUBS ===\n{sanctioned}")

    upstream = state.get("upstream_tasks", "")
    if upstream:
        parts.append(
            f"=== UPSTREAM DEPENDENCIES (tasks this one depends on) ===\n"
            f"{truncate(upstream, 6000)}"
        )

    downstream = state.get("downstream_tasks", "")
    if downstream:
        parts.append(
            f"=== DOWNSTREAM DEPENDENTS (tasks that depend on this one) ===\n"
            f"{truncate(downstream, 4000)}"
        )

    parts.append(f"=== FULL CHAT LOG ===\n{truncate(chat_log, 12000)}")
    user_content = "\n\n".join(parts)

    system_prompt = AGENT_PROMPTS[agent_type]

    debug(f"check: calling proxy ({len(user_content)} chars)")
    response = call_proxy(system_prompt, user_content)
    if response is None:
        debug("check: proxy returned None")
        return

    # Retry if the quibbler itself used banned vague language
    for retry in range(MAX_RETRIES):
        if not BANNED_PHRASES.search(response):
            break
        debug(f"check: banned phrase detected, retry {retry + 1}/{MAX_RETRIES}")
        retry_content = (
            f"Your previous response contained vague language "
            f"(\"graceful fallback\" or similar). This is a HARD NO. "
            f"Be specific: say exactly what should happen on failure "
            f"(raise X, return empty list, log warning and skip, etc). "
            f"Rewrite your entire response.\n\n"
            f"Previous response:\n{response}"
        )
        response = call_proxy(system_prompt, retry_content) or response

    debug(f"check: response starts with: {response[:80]}")

    if response.strip().startswith("APPROVED"):
        debug("check: agent work approved at this checkpoint")
        return

    # Write feedback for notify to pick up
    os.makedirs(QUIBBLER_DIR, exist_ok=True)
    feedback_path = os.path.join(QUIBBLER_DIR, f"{session_id}.txt")
    friendly_type = agent_type.replace("gatekeeper:", "")
    header = (
        f"QUIBBLER BS DETECTOR — {friendly_type.upper()} AGENT (step {step})\n"
        f"{'=' * 50}\n\n"
    )
    with open(feedback_path, "w") as f:
        f.write(header + response)

    debug(f"check: wrote feedback to {feedback_path}")


# ---------------------------------------------------------------------------
# notify — PreToolUse handler
# ---------------------------------------------------------------------------

def cmd_notify() -> None:
    """Check for pending feedback and inject it via stderr + exit code."""
    raw = sys.stdin.read()

    try:
        hook = json.loads(raw)
    except json.JSONDecodeError:
        return

    session_id = hook.get("session_id", "unknown")
    feedback_path = os.path.join(QUIBBLER_DIR, f"{session_id}.txt")

    if not os.path.isfile(feedback_path):
        return

    try:
        with open(feedback_path) as f:
            feedback = f.read()
        os.unlink(feedback_path)
    except OSError:
        return

    if not feedback.strip():
        return

    print(feedback, file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: quibbler.py {check|notify}", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "check":
        cmd_check()
    elif cmd == "notify":
        cmd_notify()
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
