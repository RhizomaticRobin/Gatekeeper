#!/usr/bin/env python3
"""Failure classification and adaptive retry for GSD-VGL task execution.

Classifies test/build failures into 5 types and recommends retry strategies
based on failure type and attempt count.

Functions:
  classify_failure(test_output, exit_code, test_history=None)
      -- returns dict with failure_type and confidence
  retry_strategy(failure_type, attempt_count)
      -- returns dict with action and explanation
  detect_flaky_tests(history)
      -- returns list of test names that alternate pass/fail

Failure types:
  - test_failure: assertion errors, expected/got mismatches, FAILED keywords
  - build_error: SyntaxError, ImportError, Cannot find module
  - timeout: "timed out" in output or exit code 124
  - scope_creep: changes outside file_scope detected
  - flaky_test: same test alternates pass/fail in history

CLI:
  python3 failure_classifier.py --classify --output "..." --exit-code N
  python3 failure_classifier.py --strategy --failure-type TYPE --attempt N
"""

import argparse
import collections
import json
import re
import sys


# ---------------------------------------------------------------------------
# Classification heuristics
# ---------------------------------------------------------------------------

# Each heuristic is a tuple of (failure_type, patterns, confidence_base)
# where patterns is a list of regex patterns to match against test output.

_CLASSIFICATION_RULES = [
    # Order matters: more specific patterns first
    ("scope_creep", [
        r"changes outside file_scope detected",
        r"outside.*file.?scope",
        r"scope.?creep",
    ], 0.85),
    ("timeout", [
        r"timed?\s*out",
        r"timeout",
        r"execution.*timed?\s*out",
    ], 0.9),
    ("build_error", [
        r"SyntaxError",
        r"ImportError",
        r"ModuleNotFoundError",
        r"Cannot find module",
        r"cannot find module",
        r"NameError",
        r"compilation failed",
        r"build failed",
    ], 0.85),
    ("test_failure", [
        r"FAILED",
        r"AssertionError",
        r"AssertionError",
        r"AssertError",
        r"expected\s+\S+\s+got\s+\S+",
        r"assert\s+.*==",
    ], 0.8),
]


def classify_failure(test_output, exit_code, test_history=None):
    """Classify a test failure into one of 5 failure types.

    Args:
        test_output: string of test/build output
        exit_code: integer exit code of the process
        test_history: optional list of dicts with test_name and passed keys
                      for flaky test detection

    Returns:
        dict with keys:
            failure_type: one of test_failure, build_error, timeout,
                          scope_creep, flaky_test
            confidence: float between 0.0 and 1.0
    """
    # Check for flaky tests first if history is provided
    if test_history:
        flaky_tests = detect_flaky_tests(test_history)
        if flaky_tests:
            # Check if any flaky test name appears in the output
            for test_name in flaky_tests:
                if test_name in test_output:
                    return {
                        "failure_type": "flaky_test",
                        "confidence": 0.75,
                    }

    # Check exit code 124 (timeout) first -- high confidence signal
    if exit_code == 124:
        return {
            "failure_type": "timeout",
            "confidence": 0.95,
        }

    # Apply pattern-based classification rules
    best_match = None
    best_confidence = 0.0
    matched_count = 0

    for failure_type, patterns, confidence_base in _CLASSIFICATION_RULES:
        match_count = 0
        for pattern in patterns:
            if re.search(pattern, test_output, re.IGNORECASE):
                match_count += 1

        if match_count > 0:
            # Boost confidence slightly for multiple pattern matches
            confidence = min(1.0, confidence_base + 0.05 * (match_count - 1))
            if confidence > best_confidence:
                best_confidence = confidence
                best_match = failure_type
                matched_count = match_count

    if best_match:
        return {
            "failure_type": best_match,
            "confidence": best_confidence,
        }

    # Fallback: unknown failure, classify as test_failure with low confidence
    return {
        "failure_type": "test_failure",
        "confidence": 0.3,
    }


# ---------------------------------------------------------------------------
# Adaptive retry strategy
# ---------------------------------------------------------------------------

_STRATEGY_MAP = {
    1: {
        "action": "retry",
        "explanation": "First attempt failed. Retrying the same approach "
                       "as transient issues often resolve on retry.",
    },
    2: {
        "action": "modify_prompt",
        "explanation": "Second attempt failed. Modifying the prompt to "
                       "try a different approach to resolve the failure.",
    },
}

_ESCALATE = {
    "action": "escalate",
    "explanation": "Multiple retry attempts have failed. Escalating to "
                   "human review or a more capable agent for resolution.",
}


def retry_strategy(failure_type, attempt_count):
    """Determine the retry strategy based on failure type and attempt count.

    Args:
        failure_type: string, one of the 5 failure types
        attempt_count: integer, the current attempt number (1-based)

    Returns:
        dict with keys:
            action: one of retry, modify_prompt, escalate
            explanation: string explaining the chosen action
    """
    if attempt_count >= 3:
        return dict(_ESCALATE)

    base = _STRATEGY_MAP.get(attempt_count, dict(_ESCALATE))
    result = dict(base)

    # Customize explanation based on failure type
    type_context = {
        "test_failure": "Test assertions are failing.",
        "build_error": "The build or import is broken.",
        "timeout": "The process timed out.",
        "scope_creep": "Changes were detected outside the allowed file scope.",
        "flaky_test": "The test appears to be flaky (intermittent pass/fail).",
    }

    context = type_context.get(failure_type, "")
    if context:
        result["explanation"] = f"{context} {result['explanation']}"

    return result


# ---------------------------------------------------------------------------
# Flaky test detection
# ---------------------------------------------------------------------------

def detect_flaky_tests(history):
    """Detect tests that alternate between pass and fail in their history.

    A test is considered flaky if it has at least 2 results and the outcomes
    alternate (i.e., consecutive results differ at least once in each
    direction: pass->fail and fail->pass).

    Args:
        history: list of dicts with keys test_name (str) and passed (bool)

    Returns:
        list of test_name strings that are detected as flaky
    """
    if not history:
        return []

    # Group results by test name, preserving order
    test_results = collections.defaultdict(list)
    for entry in history:
        test_name = entry.get("test_name")
        passed = entry.get("passed")
        if test_name is not None and passed is not None:
            test_results[test_name].append(passed)

    flaky = []
    for test_name, results in test_results.items():
        if len(results) < 2:
            continue

        # Check for alternation: must have at least one pass->fail and one
        # fail->pass transition
        has_pass_to_fail = False
        has_fail_to_pass = False

        for i in range(1, len(results)):
            if results[i - 1] and not results[i]:
                has_pass_to_fail = True
            elif not results[i - 1] and results[i]:
                has_fail_to_pass = True

        if has_pass_to_fail and has_fail_to_pass:
            flaky.append(test_name)

    return flaky


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="GSD-VGL Failure Classification and Adaptive Retry"
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--classify", action="store_true",
                       help="Classify a failure from output and exit code")
    group.add_argument("--strategy", action="store_true",
                       help="Get retry strategy for a failure type and attempt")

    # --classify arguments
    parser.add_argument("--output", default="",
                        help="Test/build output text for --classify")
    parser.add_argument("--exit-code", type=int, default=1,
                        help="Exit code for --classify (default: 1)")

    # --strategy arguments
    parser.add_argument("--failure-type",
                        help="Failure type for --strategy")
    parser.add_argument("--attempt", type=int,
                        help="Attempt count for --strategy")

    args = parser.parse_args()

    if args.classify:
        result = classify_failure(args.output, args.exit_code)
        print(json.dumps(result, indent=2))

    elif args.strategy:
        if not args.failure_type or args.attempt is None:
            parser.error("--strategy requires --failure-type and --attempt")
        result = retry_strategy(args.failure_type, args.attempt)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
