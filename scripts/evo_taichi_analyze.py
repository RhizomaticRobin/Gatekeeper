#!/usr/bin/env python3
"""Taichi kernel AST structure analysis.

CLI:
    python3 evo_taichi_analyze.py --analyze --file F --function FN
"""

import argparse
import ast
import json
import os
import sys
from gk_log import gk_error
from evo_taichi_ast import (
    decorator_to_str,
    extract_parameters,
    call_to_name,
    find_module_fields,
    get_referenced_names,
    find_thread_range,
    find_imports_from,
)


def cmd_analyze(args):
    """Parse a Taichi kernel using AST and output structural information."""
    file_path = args.file
    function_name = args.function

    if not os.path.isfile(file_path):
        gk_error(f"File not found: {file_path}")
        print(json.dumps({"error": f"File not found: {file_path}"}))
        sys.exit(1)

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except OSError as e:
        gk_error(f"Cannot read {file_path}: {e}")
        print(json.dumps({"error": f"Cannot read {file_path}: {e}"}))
        sys.exit(1)

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as e:
        gk_error(f"SyntaxError parsing {file_path}: {e}")
        print(json.dumps({"error": f"SyntaxError: {e}"}))
        sys.exit(1)

    target_node = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == function_name:
                target_node = node
                break

    if target_node is None:
        gk_error(f"Function '{function_name}' not found in {file_path}")
        print(json.dumps({"error": f"Function '{function_name}' not found"}))
        sys.exit(1)

    # Decorators
    decorators = []
    is_ti_kernel = False
    is_ti_func = False
    for dec in target_node.decorator_list:
        dec_str = decorator_to_str(dec)
        decorators.append(dec_str)
        if dec_str == "ti.kernel":
            is_ti_kernel = True
        elif dec_str == "ti.func":
            is_ti_func = True

    # Parameters
    parameters = extract_parameters(target_node)

    # Find all @ti.func decorated functions in the module
    ti_func_names = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if decorator_to_str(dec) == "ti.func":
                    ti_func_names.add(node.name)

    # Helper function calls within the target
    helper_funcs = []
    called_names = set()
    for node in ast.walk(target_node):
        if isinstance(node, ast.Call):
            cn = call_to_name(node)
            if cn and cn in ti_func_names and cn != function_name:
                if cn not in called_names:
                    called_names.add(cn)
                    helper_funcs.append(cn)

    # Module-level field references
    module_field_names = find_module_fields(tree)
    body_names = get_referenced_names(target_node)
    field_refs = sorted([name for name in module_field_names if name in body_names])

    # Thread range
    thread_range = find_thread_range(target_node)

    # LOC count
    start = target_node.lineno - 1
    end = target_node.end_lineno if hasattr(target_node, "end_lineno") and target_node.end_lineno else start + 1
    loc = end - start

    # Imports
    imports_from = find_imports_from(tree, target_node)

    result = {
        "function_name": function_name,
        "is_ti_kernel": is_ti_kernel,
        "is_ti_func": is_ti_func,
        "decorators": decorators,
        "parameters": parameters,
        "helper_funcs": helper_funcs,
        "field_refs": field_refs,
        "thread_range": thread_range,
        "loc": loc,
        "imports_from": imports_from,
    }

    print(json.dumps(result, indent=2))


def analyze_internal(file_path, function_name):
    """Run analysis without printing — return dict or None.

    Used by evo_taichi_harness.py internally.
    """
    if not os.path.isfile(file_path):
        gk_error(f"File not found: {file_path}")
        return None

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except OSError as e:
        gk_error(f"Cannot read {file_path}: {e}")
        return None

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as e:
        gk_error(f"SyntaxError parsing {file_path}: {e}")
        return None

    target_node = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == function_name:
                target_node = node
                break

    if target_node is None:
        gk_error(f"Function '{function_name}' not found in {file_path}")
        return None

    decorators = []
    is_ti_kernel = False
    is_ti_func = False
    for dec in target_node.decorator_list:
        dec_str = decorator_to_str(dec)
        decorators.append(dec_str)
        if dec_str == "ti.kernel":
            is_ti_kernel = True
        elif dec_str == "ti.func":
            is_ti_func = True

    parameters = extract_parameters(target_node)

    ti_func_names = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if decorator_to_str(dec) == "ti.func":
                    ti_func_names.add(node.name)

    helper_funcs = []
    called_names = set()
    for node in ast.walk(target_node):
        if isinstance(node, ast.Call):
            cn = call_to_name(node)
            if cn and cn in ti_func_names and cn != function_name:
                if cn not in called_names:
                    called_names.add(cn)
                    helper_funcs.append(cn)

    module_field_names = find_module_fields(tree)
    body_names = get_referenced_names(target_node)
    field_refs = sorted([name for name in module_field_names if name in body_names])

    thread_range = find_thread_range(target_node)

    start = target_node.lineno - 1
    end = target_node.end_lineno if hasattr(target_node, "end_lineno") and target_node.end_lineno else start + 1
    loc = end - start

    imports_from = find_imports_from(tree, target_node)

    return {
        "function_name": function_name,
        "file_path": file_path,
        "is_ti_kernel": is_ti_kernel,
        "is_ti_func": is_ti_func,
        "decorators": decorators,
        "parameters": parameters,
        "helper_funcs": helper_funcs,
        "field_refs": field_refs,
        "thread_range": thread_range,
        "loc": loc,
        "imports_from": imports_from,
    }


def main():
    parser = argparse.ArgumentParser(description="Taichi kernel AST analysis")
    parser.add_argument("--analyze", action="store_true", required=True)
    parser.add_argument("--file", required=True, help="Python file containing the kernel")
    parser.add_argument("--function", required=True, help="Function name to analyze")
    args = parser.parse_args()
    cmd_analyze(args)


if __name__ == "__main__":
    main()
