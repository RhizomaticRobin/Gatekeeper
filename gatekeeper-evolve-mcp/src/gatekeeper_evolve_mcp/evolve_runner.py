"""
Subprocess runner for evolve scripts.

Delegates to scripts/evo_*.py in the plugin's scripts/ directory,
passing GK_DB_PATH in the environment so scripts can use the unified SQLite database.
"""

import json
import os
import subprocess
import sys
import logging

logger = logging.getLogger(__name__)

# Resolve scripts/ directory relative to plugin root
# This module is at gatekeeper-evolve-mcp/src/gatekeeper_evolve_mcp/evolve_runner.py
# Plugin root is 3 levels up: gatekeeper-evolve-mcp -> (plugin root)
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_MODULE_DIR)))
SCRIPTS_DIR = os.path.join(_PLUGIN_ROOT, "scripts")

# CWD for subprocess invocations
SERVER_CWD = os.getcwd()

# Database path (set during server initialization)
_db_path: str = ""


def set_db_path(db_path: str) -> None:
    """Set the database path for subprocess environment injection."""
    global _db_path
    _db_path = db_path


def run_script(script_name: str, args: list, timeout: int = 300) -> dict:
    """Run a Python script from SCRIPTS_DIR and return parsed JSON output.

    Sets GK_DB_PATH in the subprocess environment so that evo_db.py and
    other scripts can use the unified SQLite database.
    """
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, script_name)] + args
    logger.info(f"Running: {' '.join(cmd)}")

    env = os.environ.copy()
    if _db_path:
        env["GK_DB_PATH"] = _db_path

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=SERVER_CWD,
        env=env,
    )

    if result.stderr:
        logger.debug(f"stderr: {result.stderr[:500]}")

    if result.returncode != 0:
        return {"error": f"Script exited with code {result.returncode}", "stderr": result.stderr[:1000]}

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw_output": result.stdout[:2000]}


def run_script_raw(script_name: str, args: list, timeout: int = 60) -> str:
    """Run a Python script and return raw stdout (for text-output tools like extract_function)."""
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, script_name)] + args
    logger.info(f"Running: {' '.join(cmd)}")

    env = os.environ.copy()
    if _db_path:
        env["GK_DB_PATH"] = _db_path

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=SERVER_CWD,
        env=env,
    )

    if result.returncode != 0:
        return f"ERROR: {result.stderr[:1000]}"

    return result.stdout
