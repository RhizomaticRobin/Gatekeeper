#!/usr/bin/env python3
"""Function extraction, mutation, and replacement for Hyperphase N (evolutionary optimization).

Provides operations on individual Python functions within files:
  --extract: Extract a function with EVOLVE-BLOCK-START/END markers
  --extract-bundle: Extract Taichi kernel bundle with all dependencies
  --apply-diff: Apply a SEARCH/REPLACE diff to a function
  --replace: Replace a function with optimized code (creates backup)
  --revert: Restore a function from its most recent backup

All write operations create a .bak_{timestamp} backup first.

CLI:
    python3 evo_block.py --extract --file F --function FN
    python3 evo_block.py --extract-bundle --file F --function FN
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
from gk_log import gk_error, gk_warn
from evo_taichi_ast import (
    get_decorators,
    has_taichi_decorator,
    collect_called_names,
    get_referenced_names,
    is_ti_field_call,
    collect_imports,
)


def find_function(source, function_name):
    """Find a function in source code using AST.

    Returns (start_line, end_line, func_source) or None.
    Lines are 0-indexed.

    If the function has decorators, the start line includes the first
    decorator so that @ti.kernel, @ti.func, etc. are captured.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        gk_error(f"SyntaxError parsing source — cannot locate function '{function_name}': {e}")
        return None  # Callers MUST check for None and handle as a hard error

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == function_name:
                # Include decorators in the extraction range
                if node.decorator_list:
                    start = node.decorator_list[0].lineno - 1  # 0-indexed
                else:
                    start = node.lineno - 1  # 0-indexed
                end = node.end_lineno if hasattr(node, "end_lineno") and node.end_lineno else start + 1
                lines = source.splitlines()
                func_lines = lines[start:end]
                return start, end, "\n".join(func_lines)

    return None


def find_taichi_bundle(source, function_name):
    """Find a Taichi kernel/func and all its dependencies as a bundle.

    Returns a dict with keys: target, helpers, fields, imports.
    Returns None if the function is not found.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        gk_error(f"SyntaxError parsing source — cannot locate function '{function_name}': {e}")
        return None

    lines = source.splitlines()

    # --- Step 1: Find all top-level function defs and classify them ---
    all_funcs = {}  # name -> ast node
    ti_func_names = set()  # names of @ti.func functions

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            all_funcs[node.name] = node
            if has_taichi_decorator(node, "func"):
                ti_func_names.add(node.name)

    # --- Step 2: Find the target function ---
    target_node = None
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == function_name:
                target_node = node
                break

    if target_node is None:
        # Also search nested (in case of class methods etc.)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == function_name:
                    target_node = node
                    break

    if target_node is None:
        return None

    # Get target info
    if target_node.decorator_list:
        target_start = target_node.decorator_list[0].lineno - 1
    else:
        target_start = target_node.lineno - 1
    target_end = target_node.end_lineno if hasattr(target_node, "end_lineno") and target_node.end_lineno else target_start + 1
    target_source = "\n".join(lines[target_start:target_end])
    target_decorators = get_decorators(target_node)

    target_info = {
        "name": function_name,
        "source": target_source,
        "start_line": target_start + 1,  # 1-indexed for output
        "end_line": target_end,
        "decorators": target_decorators,
    }

    # --- Step 3: Collect imports (from ... import ...) ---
    import_map, import_statements = collect_imports(tree, lines)

    # --- Step 4: Find all @ti.func helpers called by the target (recursively) ---
    helpers = []
    visited_helpers = set()

    def _find_helpers_recursive(func_node):
        """Recursively find all @ti.func helpers called by func_node."""
        called = collect_called_names(func_node)
        for name in called:
            if name in visited_helpers:
                continue
            if name in ti_func_names:
                visited_helpers.add(name)
                helper_node = all_funcs[name]
                if helper_node.decorator_list:
                    h_start = helper_node.decorator_list[0].lineno - 1
                else:
                    h_start = helper_node.lineno - 1
                h_end = helper_node.end_lineno if hasattr(helper_node, "end_lineno") and helper_node.end_lineno else h_start + 1
                h_source = "\n".join(lines[h_start:h_end])
                h_decorators = get_decorators(helper_node)
                helpers.append({
                    "name": name,
                    "source": h_source,
                    "start_line": h_start + 1,
                    "end_line": h_end,
                    "decorators": h_decorators,
                    "origin": "local",
                })
                # Recurse into this helper
                _find_helpers_recursive(helper_node)
            elif name in import_map:
                # This is an imported function that might be a helper
                visited_helpers.add(name)
                helpers.append({
                    "name": name,
                    "source": None,
                    "origin": f"import:{import_map[name]}",
                })

    _find_helpers_recursive(target_node)

    # --- Step 5: Find module-level ti.field references used by target or helpers ---
    fields = []

    # Collect all names referenced in target + local helpers
    all_referenced = get_referenced_names(target_node)
    for h in helpers:
        if h["origin"] == "local" and h["name"] in all_funcs:
            all_referenced |= get_referenced_names(all_funcs[h["name"]])

    # Scan top-level assignments for ti.field calls
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            # Check if rhs is a ti.field call
            if isinstance(node.value, ast.Call) and is_ti_field_call(node.value):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in all_referenced:
                        f_line = node.lineno - 1
                        f_end = node.end_lineno if hasattr(node, "end_lineno") and node.end_lineno else f_line + 1
                        f_source = "\n".join(lines[f_line:f_end])
                        fields.append({
                            "name": target.id,
                            "source": f_source,
                            "line": node.lineno,
                        })
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.value, ast.Call) and is_ti_field_call(node.value):
                if isinstance(node.target, ast.Name) and node.target.id in all_referenced:
                    f_line = node.lineno - 1
                    f_end = node.end_lineno if hasattr(node, "end_lineno") and node.end_lineno else f_line + 1
                    f_source = "\n".join(lines[f_line:f_end])
                    fields.append({
                        "name": node.target.id,
                        "source": f_source,
                        "line": node.lineno,
                    })

    # --- Step 6: Collect relevant import statements ---
    # Find which imports are actually used by the target + helpers
    relevant_imports = []
    for module, names_list, stmt_source in import_statements:
        # Check if any imported name is referenced
        relevant_names = []
        for n in names_list:
            # Handle "name as alias" form
            actual_name = n.split(" as ")[-1].strip() if " as " in n else n.strip()
            if actual_name in all_referenced:
                relevant_names.append(n)
        if relevant_names:
            relevant_imports.append(stmt_source)

    return {
        "target": target_info,
        "helpers": helpers,
        "fields": fields,
        "imports": relevant_imports,
    }


def extract_bundle(file_path, function_name):
    """Extract a Taichi kernel bundle and print as markdown-formatted text."""
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()

    bundle = find_taichi_bundle(source, function_name)
    if bundle is None:
        gk_error(f"Function '{function_name}' not found in {file_path}")
        sys.exit(1)

    # Format as markdown bundle
    parts = []
    parts.append(f"# EVOLVE-BUNDLE-START {function_name}")
    parts.append("")

    # Target kernel
    parts.append("## Target Kernel")
    parts.append(bundle["target"]["source"])
    parts.append("")

    # Local helpers
    local_helpers = [h for h in bundle["helpers"] if h["origin"] == "local"]
    if local_helpers:
        parts.append("## Helper Functions (local)")
        for h in local_helpers:
            parts.append(h["source"])
            parts.append("")

    # Imported helpers
    imported_helpers = [h for h in bundle["helpers"] if h["origin"] != "local"]
    if imported_helpers:
        parts.append("## Helper Functions (imported)")
        # Group by origin module
        by_module = {}
        for h in imported_helpers:
            module = h["origin"].replace("import:", "")
            if module not in by_module:
                by_module[module] = []
            by_module[module].append(h["name"])
        for module, names in by_module.items():
            parts.append(f"# From {module}:")
            parts.append(f"#   {', '.join(names)}")
        parts.append("")

    # Module-level fields
    if bundle["fields"]:
        parts.append("## Module-Level Fields")
        for field in bundle["fields"]:
            parts.append(field["source"])
        parts.append("")

    # Relevant imports
    if bundle["imports"]:
        parts.append("## Imports")
        for imp in bundle["imports"]:
            parts.append(imp)
        parts.append("")

    parts.append(f"# EVOLVE-BUNDLE-END {function_name}")

    print("\n".join(parts))


def extract_function(file_path, function_name):
    """Extract a function and wrap with EVOLVE-BLOCK markers."""
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()

    result = find_function(source, function_name)
    if result is None:
        gk_error(f"Function '{function_name}' not found in {file_path}")
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
    group.add_argument("--extract-bundle", action="store_true",
                       help="Extract Taichi kernel bundle with dependencies")
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

    elif args.extract_bundle:
        extract_bundle(args.file, args.function)

    elif args.apply_diff:
        if not args.diff_file:
            gk_error("--diff-file required for --apply-diff")
            sys.exit(1)
        with open(args.diff_file, "r") as f:
            diff_content = f.read()
        apply_diff(args.file, args.function, diff_content)

    elif args.replace:
        if not args.source_file:
            gk_error("--source-file required for --replace")
            sys.exit(1)
        with open(args.source_file, "r") as f:
            new_code = f.read()
        replace_function_in_file(args.file, args.function, new_code)

    elif args.revert:
        revert_function_in_file(args.file, args.function)


if __name__ == "__main__":
    main()
