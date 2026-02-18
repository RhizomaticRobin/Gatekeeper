#!/usr/bin/env python3
"""Function extraction, mutation, and replacement for Hyperphase N (evolutionary optimization).

Provides operations on individual Python functions within files:
  --extract: Extract a function with EVOLVE-BLOCK-START/END markers
  --apply-diff: Apply a SEARCH/REPLACE diff to a function
  --replace: Replace a function with optimized code (creates backup)
  --revert: Restore a function from its most recent backup

All write operations create a .bak_{timestamp} backup first.

CLI:
    python3 evo_block.py --extract --file F --function FN
    python3 evo_block.py --apply-diff --file F --function FN --diff-file D
    python3 evo_block.py --replace --file F --function FN --source-file SRC
    python3 evo_block.py --revert --file F --function FN
"""

import argparse
import ast
import glob
import json
import os
import re
import shutil
import sys
import time


def find_function(source, function_name):
    """Find a function in source code using AST.

    Returns (start_line, end_line, func_source) or None.
    Lines are 0-indexed.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"SyntaxError parsing source: {e}", file=sys.stderr)
        return None

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == function_name:
                start = node.lineno - 1  # 0-indexed
                end = node.end_lineno if hasattr(node, "end_lineno") and node.end_lineno else start + 1
                lines = source.splitlines()
                func_lines = lines[start:end]
                return start, end, "\n".join(func_lines)

    return None


def extract_function(file_path, function_name):
    """Extract a function and wrap with EVOLVE-BLOCK markers."""
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()

    result = find_function(source, function_name)
    if result is None:
        print(f"ERROR: Function '{function_name}' not found in {file_path}", file=sys.stderr)
        sys.exit(1)

    _start, _end, func_source = result
    output = f"# EVOLVE-BLOCK-START {function_name}\n{func_source}\n# EVOLVE-BLOCK-END {function_name}"
    print(output)


def apply_diff(file_path, function_name, diff_content):
    """Apply a SEARCH/REPLACE diff to a function in a file.

    Diff format:
        <<<SEARCH
        old code
        =======
        new code
        >>>REPLACE
    """
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()

    result = find_function(source, function_name)
    if result is None:
        print(json.dumps({"success": False, "error": f"Function '{function_name}' not found"}))
        return

    start, end, func_source = result

    # Parse SEARCH/REPLACE blocks
    pattern = r"<<<SEARCH\n(.*?)\n=======\n(.*?)\n>>>REPLACE"
    matches = re.findall(pattern, diff_content, re.DOTALL)

    if not matches:
        print(json.dumps({"success": False, "error": "No SEARCH/REPLACE blocks found in diff"}))
        return

    # Create backup
    backup_path = create_backup(file_path)

    # Apply each replacement to the function source
    modified_func = func_source
    for search, replace in matches:
        if search.strip() in modified_func:
            modified_func = modified_func.replace(search.strip(), replace.strip(), 1)
        else:
            # Try fuzzy match (strip leading whitespace from each line)
            search_stripped = "\n".join(line.strip() for line in search.strip().splitlines())
            func_stripped = "\n".join(line.strip() for line in modified_func.splitlines())
            if search_stripped in func_stripped:
                # Reconstruct with original indentation preserved in replace
                modified_func = modified_func.replace(search.strip(), replace.strip(), 1)
            else:
                print(json.dumps({
                    "success": False,
                    "error": f"SEARCH block not found in function",
                    "search_preview": search.strip()[:200],
                }))
                # Restore from backup
                shutil.copy2(backup_path, file_path)
                return

    # Replace function in source
    lines = source.splitlines()
    new_lines = lines[:start] + modified_func.splitlines() + lines[end:]
    new_source = "\n".join(new_lines)

    # Validate syntax
    try:
        ast.parse(new_source)
    except SyntaxError as e:
        print(json.dumps({"success": False, "error": f"Syntax error after applying diff: {e}"}))
        shutil.copy2(backup_path, file_path)
        return

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_source)

    print(json.dumps({"success": True, "applied_code": modified_func, "backup": backup_path}))


def replace_function_in_file(file_path, function_name, new_code):
    """Replace a function body with new code."""
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()

    result = find_function(source, function_name)
    if result is None:
        print(json.dumps({"success": False, "error": f"Function '{function_name}' not found"}))
        return

    start, end, _old_func = result

    # Create backup
    backup_path = create_backup(file_path)

    # Replace
    lines = source.splitlines()
    new_lines = lines[:start] + new_code.strip().splitlines() + lines[end:]
    new_source = "\n".join(new_lines)

    # Validate syntax
    try:
        ast.parse(new_source)
    except SyntaxError as e:
        print(json.dumps({"success": False, "error": f"Syntax error in replacement: {e}"}))
        shutil.copy2(backup_path, file_path)
        return

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_source)

    print(json.dumps({"success": True, "backup": backup_path}))


def revert_function_in_file(file_path, function_name):
    """Restore a file from its most recent .bak_* backup."""
    dir_path = os.path.dirname(file_path) or "."
    basename = os.path.basename(file_path)
    pattern = os.path.join(dir_path, f"{basename}.bak_*")
    backups = sorted(glob.glob(pattern))

    if not backups:
        print(json.dumps({"success": False, "error": f"No backups found for {file_path}"}))
        return

    latest_backup = backups[-1]
    shutil.copy2(latest_backup, file_path)
    print(json.dumps({"success": True, "restored_from": latest_backup}))


def create_backup(file_path):
    """Create a timestamped backup of a file."""
    timestamp = int(time.time())
    backup_path = f"{file_path}.bak_{timestamp}"
    shutil.copy2(file_path, backup_path)
    return backup_path


def main():
    parser = argparse.ArgumentParser(description="Function extraction and mutation for Hyperphase N")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--extract", action="store_true", help="Extract function with EVOLVE-BLOCK markers")
    group.add_argument("--apply-diff", action="store_true", help="Apply SEARCH/REPLACE diff to function")
    group.add_argument("--replace", action="store_true", help="Replace function with new code")
    group.add_argument("--revert", action="store_true", help="Revert function from backup")

    parser.add_argument("--file", required=True, help="Target Python file")
    parser.add_argument("--function", required=True, help="Function name")
    parser.add_argument("--diff-file", help="Path to diff file (for --apply-diff)")
    parser.add_argument("--source-file", help="Path to source file with new code (for --replace)")

    args = parser.parse_args()

    if args.extract:
        extract_function(args.file, args.function)

    elif args.apply_diff:
        if not args.diff_file:
            print("ERROR: --diff-file required for --apply-diff", file=sys.stderr)
            sys.exit(1)
        with open(args.diff_file, "r") as f:
            diff_content = f.read()
        apply_diff(args.file, args.function, diff_content)

    elif args.replace:
        if not args.source_file:
            print("ERROR: --source-file required for --replace", file=sys.stderr)
            sys.exit(1)
        with open(args.source_file, "r") as f:
            new_code = f.read()
        replace_function_in_file(args.file, args.function, new_code)

    elif args.revert:
        revert_function_in_file(args.file, args.function)


if __name__ == "__main__":
    main()
