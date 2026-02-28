"""
Shared subprocess execution utility for verification tools.

Provides async subprocess execution with timeout, stdout/stderr capture,
and configurable working directory and environment variables.

This is NOT an MCP tool module -- it does not have register_tools().
It is imported directly by tool modules (prusti.py, kani.py, etc.).

Usage:
    from gatekeeper_mcp.tools.verification_runner import run_subprocess, SubprocessResult

    result = await run_subprocess(
        cmd=['cargo', 'prusti'],
        timeout=120,
        cwd='/path/to/project',
        env={'PRUSTI_COUNTEREXAMPLE': 'true'}
    )
    if result.timed_out:
        # handle timeout
    elif result.returncode != 0:
        # handle error, parse result.stderr
    else:
        # success, parse result.stdout
"""

import asyncio
import os
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SubprocessResult:
    """Result of a subprocess execution."""
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


async def run_subprocess(
    cmd: list[str],
    timeout: int = 120,
    cwd: Optional[str] = None,
    env: Optional[dict] = None
) -> SubprocessResult:
    """
    Run a subprocess asynchronously with timeout and output capture.

    Args:
        cmd: Command and arguments as list of strings (e.g., ['cargo', 'prusti'])
        timeout: Maximum execution time in seconds (default: 120)
        cwd: Working directory for the subprocess (default: current directory)
        env: Additional environment variables (merged with os.environ; overrides existing)

    Returns:
        SubprocessResult with returncode, stdout, stderr, and timed_out flag

    Note:
        On timeout, the process is killed (SIGKILL) and SubprocessResult is returned
        with timed_out=True, returncode=-1, and any partially captured output.
    """
    # Merge env with os.environ if provided
    full_env = None
    if env is not None:
        full_env = {**os.environ, **env}

    logger.info(f"Running subprocess: {' '.join(cmd)}", extra={
        'tool_name': 'verification_runner',
        'cmd': cmd,
        'timeout': timeout,
        'cwd': cwd
    })

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=full_env
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout
        )
        stdout = stdout_bytes.decode('utf-8', errors='replace')
        stderr = stderr_bytes.decode('utf-8', errors='replace')

        logger.info(f"Subprocess completed: returncode={process.returncode}", extra={
            'tool_name': 'verification_runner',
            'returncode': process.returncode
        })

        return SubprocessResult(
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=False
        )

    except asyncio.TimeoutError:
        logger.warning(f"Subprocess timed out after {timeout}s, killing process", extra={
            'tool_name': 'verification_runner',
            'cmd': cmd
        })

        # Kill the process
        try:
            process.kill()
            await process.wait()
        except ProcessLookupError:
            pass  # Process already exited

        # Try to capture any partial output
        stdout = ''
        stderr = ''
        try:
            if process.stdout:
                partial = await asyncio.wait_for(process.stdout.read(), timeout=1)
                stdout = partial.decode('utf-8', errors='replace')
            if process.stderr:
                partial = await asyncio.wait_for(process.stderr.read(), timeout=1)
                stderr = partial.decode('utf-8', errors='replace')
        except (asyncio.TimeoutError, Exception):
            pass

        return SubprocessResult(
            returncode=-1,
            stdout=stdout,
            stderr=stderr,
            timed_out=True
        )
