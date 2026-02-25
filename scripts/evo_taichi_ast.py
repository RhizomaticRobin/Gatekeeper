#!/usr/bin/env python3
"""Shared Taichi AST utilities for evo_block.py and evo_taichi_*.py.

Consolidates duplicated AST helper functions into a single module.
All functions are pure AST operations — no Taichi import needed.
"""

import ast


# ======================================================================
# Node-to-string conversions
# ======================================================================

def node_to_str(node):
    """Convert a simple AST node (Name, Attribute chain) to string."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return f"{node_to_str(node.value)}.{node.attr}"
    return ast.dump(node)


def expr_to_str(node):
    """Best-effort conversion of an expression AST node to source string."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Constant):
        return repr(node.value)
    elif isinstance(node, ast.Attribute):
        return node_to_str(node)
    elif isinstance(node, ast.Call):
        func_str = expr_to_str(node.func)
        args = [expr_to_str(a) for a in node.args]
        return f"{func_str}({', '.join(args)})"
    elif isinstance(node, ast.BinOp):
        left = expr_to_str(node.left)
        right = expr_to_str(node.right)
        op = binop_to_str(node.op)
        return f"{left} {op} {right}"
    elif isinstance(node, ast.UnaryOp):
        operand = expr_to_str(node.operand)
        op = unaryop_to_str(node.op)
        return f"{op}{operand}"
    elif isinstance(node, ast.Subscript):
        value = expr_to_str(node.value)
        sl = expr_to_str(node.slice)
        return f"{value}[{sl}]"
    elif isinstance(node, ast.Tuple):
        elts = [expr_to_str(e) for e in node.elts]
        return f"({', '.join(elts)})"
    elif isinstance(node, ast.List):
        elts = [expr_to_str(e) for e in node.elts]
        return f"[{', '.join(elts)}]"
    else:
        try:
            return ast.unparse(node)
        except AttributeError:
            return "..."


def binop_to_str(op):
    """Convert a BinOp to its string symbol."""
    ops = {
        ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
        ast.FloorDiv: "//", ast.Mod: "%", ast.Pow: "**",
        ast.LShift: "<<", ast.RShift: ">>",
        ast.BitOr: "|", ast.BitXor: "^", ast.BitAnd: "&",
    }
    return ops.get(type(op), "?")


def unaryop_to_str(op):
    """Convert a UnaryOp to its string symbol."""
    ops = {ast.UAdd: "+", ast.USub: "-", ast.Not: "not ", ast.Invert: "~"}
    return ops.get(type(op), "?")


# ======================================================================
# Decorator helpers
# ======================================================================

def decorator_to_str(dec_node):
    """Convert a decorator AST node to a readable string.

    Handles @ti.kernel, @ti.func, @name, @a.b.c, @decorator(args).
    """
    if isinstance(dec_node, ast.Attribute):
        value_str = decorator_to_str(dec_node.value)
        return f"{value_str}.{dec_node.attr}"
    elif isinstance(dec_node, ast.Name):
        return dec_node.id
    elif isinstance(dec_node, ast.Call):
        return decorator_to_str(dec_node.func)
    else:
        return ast.dump(dec_node)


def get_decorators(node):
    """Return a list of decorator source strings for a function node."""
    return [f"@{decorator_to_str(dec)}" for dec in node.decorator_list]


def is_taichi_decorator(dec, kind):
    """Check if a decorator node is @ti.<kind> (e.g., @ti.kernel or @ti.func)."""
    if isinstance(dec, ast.Attribute):
        if isinstance(dec.value, ast.Name) and dec.value.id == "ti" and dec.attr == kind:
            return True
    if isinstance(dec, ast.Call):
        return is_taichi_decorator(dec.func, kind)
    return False


def has_taichi_decorator(node, kind="kernel"):
    """Check if a function node has @ti.<kind> decorator."""
    for dec in node.decorator_list:
        if is_taichi_decorator(dec, kind):
            return True
    return False


def has_any_taichi_decorator(node):
    """Check if a function node has any @ti.kernel or @ti.func decorator."""
    return has_taichi_decorator(node, "kernel") or has_taichi_decorator(node, "func")


# ======================================================================
# Name/reference collection
# ======================================================================

def collect_called_names(node):
    """Walk an AST node and collect all simple function names that are called.

    Returns a set of string names. Only simple calls (foo()), not attribute calls.
    """
    names = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                names.add(child.func.id)
    return names


def call_to_name(call_node):
    """Extract function name from a Call node.

    Returns the simple name for Name calls, method name for Attribute calls, or None.
    """
    func = call_node.func
    if isinstance(func, ast.Name):
        return func.id
    elif isinstance(func, ast.Attribute):
        return func.attr
    return None


def get_referenced_names(node):
    """Walk an AST node and collect all Name references (variables, functions, etc.)."""
    names = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
    return names


# ======================================================================
# ti.field detection
# ======================================================================

def chain_starts_with_ti(node):
    """Check if an attribute/name chain starts with 'ti'."""
    if isinstance(node, ast.Name):
        return node.id == "ti"
    elif isinstance(node, ast.Attribute):
        return chain_starts_with_ti(node.value)
    return False


def is_ti_field_call(value_node):
    """Check if a value node is a call to ti.field, ti.Vector.field, etc."""
    if not isinstance(value_node, ast.Call):
        return False
    func = value_node.func
    if isinstance(func, ast.Attribute) and func.attr == "field":
        return chain_starts_with_ti(func.value)
    return False


def find_module_fields(tree):
    """Find module-level ti.field / ti.Vector.field variable names.

    Returns a set of variable names.
    """
    field_names = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            if is_ti_field_call(node.value):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        field_names.add(target.id)
        elif isinstance(node, ast.AnnAssign):
            if node.value and is_ti_field_call(node.value):
                if isinstance(node.target, ast.Name):
                    field_names.add(node.target.id)
    return field_names


# ======================================================================
# Parameter / annotation extraction
# ======================================================================

def annotation_to_str(ann_node):
    """Convert a type annotation AST node to (string, is_template)."""
    if isinstance(ann_node, ast.Call):
        func = ann_node.func
        if isinstance(func, ast.Attribute):
            value_str = node_to_str(func.value)
            call_str = f"{value_str}.{func.attr}()"
            is_template = (func.attr == "template")
            return call_str, is_template
        elif isinstance(func, ast.Name):
            return f"{func.id}()", False
        return ast.dump(ann_node), False
    if isinstance(ann_node, ast.Attribute):
        value_str = node_to_str(ann_node.value)
        return f"{value_str}.{ann_node.attr}", False
    if isinstance(ann_node, ast.Name):
        return ann_node.id, False
    if isinstance(ann_node, ast.Subscript):
        return ast.dump(ann_node), False
    return ast.dump(ann_node), False


def extract_parameters(func_node):
    """Extract parameter names and type annotations from a function node."""
    params = []
    for arg in func_node.args.args:
        name = arg.arg
        annotation = arg.annotation
        if annotation is None:
            params.append({"name": name, "type": "unknown", "is_template": False})
            continue
        ann_str, is_template = annotation_to_str(annotation)
        params.append({"name": name, "type": ann_str, "is_template": is_template})
    return params


# ======================================================================
# Thread range / iteration analysis
# ======================================================================

def find_thread_range(func_node):
    """Find the thread range from the outermost for loop in a kernel."""
    for stmt in func_node.body:
        if isinstance(stmt, ast.For):
            return extract_iter_range(stmt)
    return None


def extract_iter_range(for_node):
    """Extract the iteration range string from a for loop."""
    iter_node = for_node.iter
    if isinstance(iter_node, ast.Call):
        func = iter_node.func
        func_str = node_to_str(func) if isinstance(func, (ast.Name, ast.Attribute)) else ""
        arg_strs = [expr_to_str(arg) for arg in iter_node.args]
        for kw in iter_node.keywords:
            arg_strs.append(f"{kw.arg}={expr_to_str(kw.value)}")
        return f"{func_str}({', '.join(arg_strs)})"
    elif isinstance(iter_node, ast.Name):
        return iter_node.id
    elif isinstance(iter_node, ast.Attribute):
        return node_to_str(iter_node)
    return None


# ======================================================================
# Import scanning
# ======================================================================

def find_imports_from(tree, func_node):
    """Find modules imported via 'from X import ...' whose names appear in func body.

    Returns a sorted list of unique short module names.
    """
    body_names = get_referenced_names(func_node)

    imported_modules = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name
                imported_modules[name] = node.module

    used_modules = set()
    for name in body_names:
        if name in imported_modules:
            used_modules.add(imported_modules[name])

    short_modules = set()
    for mod in used_modules:
        parts = mod.rsplit(".", 1)
        short_modules.add(parts[-1] if len(parts) > 1 else mod)

    return sorted(short_modules)


def collect_imports(tree, lines):
    """Collect import statements with details: (module, names_list, source_text).

    Returns (import_map, import_statements) where:
      import_map: dict mapping imported_name -> module
      import_statements: list of (module, names_list, source_text) tuples
    """
    import_map = {}
    import_statements = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names_list = []
            for alias in node.names:
                imported_name = alias.asname if alias.asname else alias.name
                import_map[imported_name] = module
                names_list.append(
                    alias.name if not alias.asname else f"{alias.name} as {alias.asname}"
                )
            stmt_start = node.lineno - 1
            stmt_end = (
                node.end_lineno
                if hasattr(node, "end_lineno") and node.end_lineno
                else stmt_start + 1
            )
            import_statements.append((module, names_list, "\n".join(lines[stmt_start:stmt_end])))

    return import_map, import_statements


# ======================================================================
# Utility: parse + find function
# ======================================================================

def parse_and_find_function(file_path, function_name):
    """Parse a file and find a named function.

    Returns (tree, func_node) or raises ValueError if not found.
    """
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        source = f.read()

    tree = ast.parse(source, filename=file_path)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == function_name:
                return tree, node

    raise ValueError(f"Function '{function_name}' not found in {file_path}")
