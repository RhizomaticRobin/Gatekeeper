"""
Z3-based implication checker for contract composability verification.

Uses z3-solver Python bindings directly (not shell execution) to check whether
postconditions logically imply preconditions. If the negation of the implication
is unsatisfiable, the contracts are composable.

This module is a pure logic utility -- no MCP tool registration, no database.
It is consumed by composability.py which wraps it as an MCP tool.

Usage:
    from gatekeeper_mcp.tools.z3_checker import check_implication, CheckResult

    result = check_implication(
        postconditions=["x > 0", "y >= x"],
        preconditions=["x > 0"],
        variables={"x": "Int", "y": "Int"},
        timeout_ms=5000
    )
    if result.status == 'pass':
        print("Composable!")
    elif result.status == 'fail':
        print(f"Not composable. Counterexample: {result.counterexample}")
    elif result.status == 'error':
        print(f"Error: {result.error_message}")
"""

import logging
import threading
from dataclasses import dataclass
from typing import Optional

import z3

logger = logging.getLogger(__name__)


# Z3 type constructors mapped by string name
_Z3_TYPE_MAP = {
    'Int': z3.Int,
    'Real': z3.Real,
    'Bool': z3.Bool,
}


@dataclass
class CheckResult:
    """Result of an implication check.

    Attributes:
        status: 'pass' (unsat = composable), 'fail' (sat = non-composable), 'error' (timeout/parse failure)
        counterexample: When status='fail', dict mapping variable names to their values in the counterexample
        error_message: When status='error', human-readable error description
    """
    status: str  # 'pass', 'fail', 'error'
    counterexample: Optional[dict] = None
    error_message: Optional[str] = None


def parse_variables(var_decls: dict[str, str]) -> dict[str, z3.ExprRef]:
    """
    Parse variable declarations into z3 variable objects.

    Args:
        var_decls: Dict mapping variable name to type string.
                   Supported types: 'Int', 'Real', 'Bool'
                   Example: {"x": "Int", "y": "Real", "flag": "Bool"}

    Returns:
        Dict mapping variable name to z3 expression reference.

    Raises:
        ValueError: If an unsupported type string is provided.
    """
    variables = {}
    for name, type_str in var_decls.items():
        constructor = _Z3_TYPE_MAP.get(type_str)
        if constructor is None:
            raise ValueError(
                f"Unsupported z3 type '{type_str}' for variable '{name}'. "
                f"Supported types: {list(_Z3_TYPE_MAP.keys())}"
            )
        variables[name] = constructor(name)
    return variables


def parse_expression(expr_str: str, variables: dict[str, z3.ExprRef]) -> z3.BoolRef:
    """
    Parse a string expression into a z3 BoolRef using eval.

    The expression is evaluated with z3 functions (And, Or, Not, Implies, If, etc.)
    and the declared variables in scope.

    Args:
        expr_str: Python-syntax expression string, e.g. "x > 0", "And(x > 0, y < 10)"
        variables: Dict of z3 variable objects from parse_variables()

    Returns:
        z3.BoolRef expression

    Raises:
        Exception: If the expression string is malformed or references undeclared variables
    """
    # Build namespace with z3 functions and declared variables
    namespace = {
        'And': z3.And,
        'Or': z3.Or,
        'Not': z3.Not,
        'Implies': z3.Implies,
        'If': z3.If,
        'ForAll': z3.ForAll,
        'Exists': z3.Exists,
        'True': z3.BoolVal(True),
        'False': z3.BoolVal(False),
        'IntVal': z3.IntVal,
        'RealVal': z3.RealVal,
        'BoolVal': z3.BoolVal,
    }
    namespace.update(variables)

    try:
        result = eval(expr_str, {"__builtins__": {}}, namespace)
        return result
    except Exception as e:
        raise ValueError(f"Failed to parse z3 expression '{expr_str}': {e}") from e


def check_implication(
    postconditions: list[str],
    preconditions: list[str],
    variables: dict[str, str],
    timeout_ms: int = 5000
) -> CheckResult:
    """
    Check if postconditions logically imply preconditions.

    Constructs: NOT(AND(postconditions) IMPLIES AND(preconditions))
    If this is UNSAT, the implication holds (composable).
    If this is SAT, the implication fails (non-composable) and a counterexample is extracted.

    Uses z3.Solver with push/pop for incremental checking.
    Uses threading.Timer to enforce timeout since z3's native timeout is unreliable.

    Args:
        postconditions: List of z3-parseable expression strings (module A's guarantees)
        preconditions: List of z3-parseable expression strings (module B's requirements)
        variables: Dict mapping variable name to type string ('Int', 'Real', 'Bool')
        timeout_ms: Timeout in milliseconds for the solver (default: 5000)

    Returns:
        CheckResult with:
        - status='pass' if UNSAT (composable)
        - status='fail' if SAT (non-composable), with counterexample dict
        - status='error' if timeout or parse failure, with error_message
    """
    # Handle edge cases
    if not preconditions:
        # If there are no preconditions to satisfy, composability is trivially true
        return CheckResult(status='pass')

    if not postconditions:
        # If there are no postconditions but there are preconditions,
        # we can't guarantee anything -- check if preconditions are tautologies
        # By treating empty postconditions as True
        pass  # Fall through to normal logic; AND of empty list = True

    try:
        # Parse variables
        z3_vars = parse_variables(variables)
    except ValueError as e:
        return CheckResult(status='error', error_message=str(e))

    try:
        # Parse postcondition expressions
        post_exprs = []
        for expr_str in postconditions:
            post_exprs.append(parse_expression(expr_str, z3_vars))

        # Parse precondition expressions
        pre_exprs = []
        for expr_str in preconditions:
            pre_exprs.append(parse_expression(expr_str, z3_vars))
    except (ValueError, Exception) as e:
        return CheckResult(status='error', error_message=str(e))

    # Build the implication check:
    # NOT(AND(postconditions) IMPLIES AND(preconditions))
    # If UNSAT, the implication holds.
    post_and = z3.And(*post_exprs) if post_exprs else z3.BoolVal(True)
    pre_and = z3.And(*pre_exprs) if pre_exprs else z3.BoolVal(True)
    negated_implication = z3.Not(z3.Implies(post_and, pre_and))

    # Create solver with push/pop for incremental checking
    solver = z3.Solver()
    solver.push()
    solver.add(negated_implication)

    # Use threading.Timer for reliable timeout enforcement
    timeout_seconds = timeout_ms / 1000.0
    timer = threading.Timer(timeout_seconds, solver.interrupt)
    timer.start()

    try:
        result = solver.check()
    finally:
        timer.cancel()

    # Extract model BEFORE pop (model is only valid while assertions are on the stack)
    if result == z3.sat:
        model = solver.model()
        counterexample = {str(d): str(model[d]) for d in model.decls()}
        solver.pop()
        logger.info("Composability check: FAIL (sat - non-composable, counterexample found)")
        return CheckResult(status='fail', counterexample=counterexample)

    solver.pop()

    if result == z3.unsat:
        # Implication holds -- postconditions DO imply preconditions
        logger.info("Composability check: PASS (unsat - implication holds)")
        return CheckResult(status='pass')
    elif result == z3.unknown:
        # Timeout or other solver issue
        reason = solver.reason_unknown()
        logger.warning(f"Composability check: UNKNOWN (reason: {reason})")
        return CheckResult(status='error', error_message='timeout')

    # Fallback (should not reach here)
    return CheckResult(status='error', error_message='unexpected solver state')
