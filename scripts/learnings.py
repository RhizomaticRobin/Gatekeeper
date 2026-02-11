#!/usr/bin/env python3
"""Learnings Accumulator for GSD-VGL.

Extracts structured learning entries from verifier feedback, stores them
in a JSONL file, and retrieves relevant learnings for future task prompts.

Functions:
  extract_learning(task_id, verifier_feedback, outcome) — parse feedback into structured entry
  store_learning(learning, storage_path=None)           — append to .planning/learnings.jsonl
  get_learnings(task_type=None, storage_path=None)      — list all, optionally filtered
  get_relevant_learnings(task_context, storage_path=None) — match by file patterns and task type
  get_strategy_advice(task_context, patterns, history)   — recommend iteration_budget and prompt_additions

CLI:
  python3 learnings.py --extract <task_id> <feedback> <outcome>
  python3 learnings.py --query [--task-type TYPE] [--storage PATH]
  python3 learnings.py --relevant <context_json> [--storage PATH]
  python3 learnings.py --strategy <context_json> [--history-dir DIR]

Learning schema:
  {"task_id", "category", "description", "file_patterns", "task_type", "timestamp"}

Categories: "fix_pattern", "test_pattern", "dependency", "configuration", "approach"
"""

import json
import os
import re
import sys
from datetime import datetime, timezone


# Default storage location
DEFAULT_STORAGE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".planning", "learnings.jsonl"
)

# Patterns used to extract file paths from feedback text
_FILE_PATH_RE = re.compile(
    r'(?:^|[\s,;(])('                     # preceding whitespace or punctuation
    r'(?:[a-zA-Z0-9_\-]+/)+?'             # directory components (at least one dir/)
    r'[a-zA-Z0-9_\-]+\.[a-zA-Z0-9]{1,10}' # filename.ext
    r')'
)

# Category classification patterns — order matters (first match wins)
_CATEGORY_PATTERNS = [
    (
        "test_pattern",
        re.compile(
            r'(?:test\s+(?:was|is|needs?|should|requires?|flaky|timing|assert|waitFor|async))'
            r'|(?:flaky\s+test)'
            r'|(?:test\s+needs)'
            r'|(?:the\s+test\s+needs)',
            re.IGNORECASE,
        ),
    ),
    (
        "dependency",
        re.compile(
            r'(?:missing\s+(?:dependency|package|import|module))'
            r'|(?:need\s+to\s+install)'
            r'|(?:import\s+was\s+missing)'
            r'|(?:(?:install|add)\s+package)',
            re.IGNORECASE,
        ),
    ),
    (
        "configuration",
        re.compile(
            r'(?:(?:environment|env)\s+variable)'
            r'|(?:config(?:uration)?\s+(?:file|entry|was\s+missing|not\s+set))'
            r'|(?:\.env\s+(?:config|file))'
            r'|(?:was\s+not\s+set\s+in)',
            re.IGNORECASE,
        ),
    ),
    (
        "fix_pattern",
        re.compile(
            r'(?:fixed\s+by)'
            r'|(?:root\s+cause)'
            r'|(?:the\s+(?:issue|problem|bug)\s+was)'
            r'|(?:adding\s+(?:null\s+check|validation|guard))',
            re.IGNORECASE,
        ),
    ),
    # "approach" is the fallback — no pattern needed
]


def _classify_category(feedback):
    """Classify feedback text into a category.

    Checks patterns in order; falls back to 'approach'.
    """
    for category, pattern in _CATEGORY_PATTERNS:
        if pattern.search(feedback):
            return category
    return "approach"


def _extract_file_patterns(text):
    """Extract file path patterns from feedback text."""
    matches = _FILE_PATH_RE.findall(text)
    # Deduplicate while preserving order
    seen = set()
    result = []
    for m in matches:
        m = m.strip()
        if m and m not in seen:
            seen.add(m)
            result.append(m)
    return result


def _infer_task_type(feedback, file_patterns):
    """Infer task type from feedback and file patterns.

    Heuristic based on file extensions and keywords.
    """
    text = feedback.lower()
    all_text = text + " " + " ".join(file_patterns)

    frontend_signals = [".tsx", ".jsx", ".css", ".scss", ".vue", "component", "render", "ui"]
    backend_signals = [".py", ".rs", ".go", ".java", ".sql", "api", "route", "middleware", "database", "server"]
    test_signals = ["test", "spec", ".test.", ".spec."]
    config_signals = [".yaml", ".yml", ".json", ".toml", ".env", "config", "dockerfile"]

    scores = {"frontend": 0, "backend": 0, "test": 0, "configuration": 0}
    for signal in frontend_signals:
        if signal in all_text:
            scores["frontend"] += 1
    for signal in backend_signals:
        if signal in all_text:
            scores["backend"] += 1
    for signal in test_signals:
        if signal in all_text:
            scores["test"] += 1
    for signal in config_signals:
        if signal in all_text:
            scores["configuration"] += 1

    if max(scores.values()) == 0:
        return "general"
    return max(scores, key=scores.get)


def extract_learning(task_id, verifier_feedback, outcome):
    """Parse verifier feedback into a structured learning entry.

    Args:
        task_id: The task ID (e.g. "1.1")
        verifier_feedback: Free-text feedback from the verifier
        outcome: "pass" or "fail"

    Returns:
        dict with keys: task_id, category, description, file_patterns,
                        task_type, timestamp
    """
    category = _classify_category(verifier_feedback)
    file_patterns = _extract_file_patterns(verifier_feedback)
    task_type = _infer_task_type(verifier_feedback, file_patterns)

    # Description: use the feedback directly, trimmed
    description = verifier_feedback.strip()

    return {
        "task_id": str(task_id),
        "category": category,
        "description": description,
        "file_patterns": file_patterns,
        "task_type": task_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def store_learning(learning, storage_path=None):
    """Append a learning entry to the JSONL storage file.

    Args:
        learning: dict with the learning schema fields
        storage_path: path to JSONL file (default: .planning/learnings.jsonl)
    """
    if storage_path is None:
        storage_path = DEFAULT_STORAGE_PATH

    # Ensure parent directory exists
    parent_dir = os.path.dirname(storage_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    with open(storage_path, "a") as f:
        f.write(json.dumps(learning, ensure_ascii=False) + "\n")


def get_learnings(task_type=None, storage_path=None):
    """Read all learnings, optionally filtered by task_type.

    Args:
        task_type: if provided, only return learnings with this task_type
        storage_path: path to JSONL file

    Returns:
        list of learning dicts
    """
    if storage_path is None:
        storage_path = DEFAULT_STORAGE_PATH

    if not os.path.exists(storage_path):
        return []

    learnings = []
    with open(storage_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if task_type is not None and entry.get("task_type") != task_type:
                continue
            learnings.append(entry)
    return learnings


def _compute_relevance_score(learning, task_context):
    """Compute a relevance score for a learning given a task context.

    Scoring:
      - Exact file path match: +3 per match
      - Shared directory (same parent dir): +1 per match
      - Exact task_type match: +2

    Returns int score (0 = no relevance).
    """
    score = 0

    context_patterns = task_context.get("file_patterns", [])
    context_task_type = task_context.get("task_type", "")
    learning_patterns = learning.get("file_patterns", [])
    learning_task_type = learning.get("task_type", "")

    # File pattern matching
    context_dirs = set()
    for p in context_patterns:
        context_dirs.add(os.path.dirname(p))

    for lp in learning_patterns:
        # Exact match
        if lp in context_patterns:
            score += 3
            continue
        # Directory overlap
        lp_dir = os.path.dirname(lp)
        if lp_dir and lp_dir in context_dirs:
            score += 1

    # Task type match
    if context_task_type and learning_task_type and context_task_type == learning_task_type:
        score += 2

    return score


def get_relevant_learnings(task_context, storage_path=None):
    """Get learnings relevant to the given task context.

    Matches by file pattern overlap and task type similarity.

    Args:
        task_context: dict with "file_patterns" (list) and "task_type" (str)
        storage_path: path to JSONL file

    Returns:
        list of learning dicts sorted by relevance (most relevant first),
        only those with score > 0
    """
    if storage_path is None:
        storage_path = DEFAULT_STORAGE_PATH

    all_learnings = get_learnings(storage_path=storage_path)

    # If context has no patterns and no task_type, nothing can match
    context_patterns = task_context.get("file_patterns", [])
    context_task_type = task_context.get("task_type", "")
    if not context_patterns and not context_task_type:
        return []

    scored = []
    for learning in all_learnings:
        score = _compute_relevance_score(learning, task_context)
        if score > 0:
            scored.append((score, learning))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored]


def format_learnings_for_prompt(learnings):
    """Format a list of learnings as bullet points for prompt injection.

    Args:
        learnings: list of learning dicts

    Returns:
        str with bullet-pointed learnings
    """
    if not learnings:
        return ""
    lines = []
    for l in learnings:
        category = l.get("category", "unknown")
        desc = l.get("description", "")
        task_id = l.get("task_id", "?")
        lines.append(f"- [{category}] (from task {task_id}): {desc}")
    return "\n".join(lines)


_DEFAULT_ITERATION_BUDGET = 3


def get_strategy_advice(task_context, patterns, history):
    """Return strategy advice based on detected patterns and history.

    Adapts iteration_budget and generates prompt_additions (warning text)
    for tasks that match known-difficult failure patterns.

    Degrades gracefully: returns sensible defaults when no patterns or
    history exist.

    Args:
        task_context: dict with "file_patterns" (list of file paths) and
                      "task_type" (str)
        patterns: list of pattern dicts from detect_patterns()
        history: list of history record dicts

    Returns:
        dict with:
            iteration_budget: int — recommended max iterations
            prompt_additions: list of str — warnings / tips for the prompt
    """
    if not patterns and not history:
        return {
            "iteration_budget": _DEFAULT_ITERATION_BUDGET,
            "prompt_additions": [],
        }

    context_files = set(task_context.get("file_patterns", []))
    budget = _DEFAULT_ITERATION_BUDGET
    prompt_additions = []

    for pattern in patterns:
        file_scope = pattern.get("file_scope", "")
        error_cat = pattern.get("error_category", "")
        count = pattern.get("count", 0)

        # Check if this pattern's file_scope matches any of the task's files
        matched = False
        for cf in context_files:
            if cf == file_scope or file_scope in cf or cf in file_scope:
                matched = True
                break

        if matched:
            # Increase budget proportional to how many times this pattern recurred
            budget_increase = min(count, 5)  # cap at +5
            budget = max(budget, _DEFAULT_ITERATION_BUDGET + budget_increase)

            warning = (
                f"WARNING: Recurring pattern detected — {error_cat} "
                f"in {file_scope} ({count} occurrences). "
                f"Consider extra caution with this file scope."
            )
            prompt_additions.append(warning)

    return {
        "iteration_budget": budget,
        "prompt_additions": prompt_additions,
    }


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="GSD-VGL Learnings Accumulator")
    parser.add_argument("--storage", default=None, help="Path to learnings.jsonl")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--extract", nargs=3, metavar=("TASK_ID", "FEEDBACK", "OUTCOME"),
                       help="Extract a learning from verifier feedback")
    group.add_argument("--query", action="store_true",
                       help="Query all learnings (optionally filtered)")
    group.add_argument("--relevant", metavar="CONTEXT_JSON",
                       help="Get relevant learnings for a task context (JSON string)")
    group.add_argument("--strategy", metavar="CONTEXT_JSON",
                       help="Get strategy advice for a task context (JSON string)")

    parser.add_argument("--task-type", default=None,
                        help="Filter by task type (used with --query)")
    parser.add_argument("--history-dir", default=None,
                        help="History directory for --strategy (default: .planning/history/)")

    args = parser.parse_args()

    if args.extract:
        task_id, feedback, outcome = args.extract
        learning = extract_learning(task_id, feedback, outcome)
        store_learning(learning, storage_path=args.storage)
        print(json.dumps(learning, indent=2))

    elif args.query:
        learnings = get_learnings(task_type=args.task_type, storage_path=args.storage)
        print(json.dumps(learnings, indent=2))

    elif args.relevant:
        context = json.loads(args.relevant)
        relevant = get_relevant_learnings(context, storage_path=args.storage)
        # Output both JSON and formatted bullets
        output = {
            "learnings": relevant,
            "formatted": format_learnings_for_prompt(relevant),
        }
        print(json.dumps(output, indent=2))

    elif args.strategy:
        # Import run_history for detect_patterns and get_all_history
        import importlib.util
        rh_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_history.py")
        spec = importlib.util.spec_from_file_location("run_history", rh_path)
        run_history = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(run_history)

        context = json.loads(args.strategy)
        all_history = run_history.get_all_history(history_dir=args.history_dir)
        patterns = run_history.detect_patterns(all_history)
        advice = get_strategy_advice(context, patterns, all_history)
        print(json.dumps(advice, indent=2))


if __name__ == "__main__":
    main()
