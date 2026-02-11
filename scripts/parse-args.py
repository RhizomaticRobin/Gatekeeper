#!/usr/bin/env python3
"""Parse VGL arguments from stdin using shlex (handles complex quoting properly).
Outputs JSON to stdout for the setup script to consume."""

import sys
import shlex
import json

raw = sys.stdin.read().strip()
try:
    tokens = shlex.split(raw)
except ValueError as e:
    print(json.dumps({"error": f"Failed to parse arguments: {e}"}))
    sys.exit(1)

prompt_parts = []
args = {
    "verification_criteria": "",
    "test_command": "",
    "verifier_model": "opus",
    "max_iterations": 0,
}

i = 0
while i < len(tokens):
    t = tokens[i]
    if t == "--verification-criteria" and i + 1 < len(tokens):
        args["verification_criteria"] = tokens[i + 1]
        i += 2
    elif t == "--test-command" and i + 1 < len(tokens):
        args["test_command"] = tokens[i + 1]
        i += 2
    elif t == "--verifier-model" and i + 1 < len(tokens):
        args["verifier_model"] = tokens[i + 1]
        i += 2
    elif t == "--max-iterations" and i + 1 < len(tokens):
        try:
            args["max_iterations"] = int(tokens[i + 1])
        except ValueError:
            print(json.dumps({"error": f"--max-iterations requires integer, got: {tokens[i+1]}"}))
            sys.exit(1)
        i += 2
    elif t in ("-h", "--help"):
        args["help"] = True
        i += 1
    else:
        prompt_parts.append(t)
        i += 1

args["prompt"] = " ".join(prompt_parts)
print(json.dumps(args))
