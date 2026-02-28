"""
State file writer for Gatekeeper Evolve MCP server.

Writes state files that stop-hook.sh reads:
- verifier-loop.local.md: YAML frontmatter with session metadata
- verifier-token.secret: Token with TEST_CMD_B64 and TEST_CMD_HASH

Uses atomic write pattern (temp file + rename) to prevent partial reads.
"""

import os
import tempfile
import base64
import hashlib
import logging
from typing import Optional

from gatekeeper_evolve_mcp.database import DatabaseManager
from gatekeeper_evolve_mcp.templates import get_template

logger = logging.getLogger(__name__)


class StateWriter:
    """Writes state files for stop-hook.sh consumption."""

    def __init__(self, project_dir: str, db: DatabaseManager):
        self.project_dir = project_dir
        self.db = db
        self.state_dir = os.path.join(project_dir, '.claude')
        os.makedirs(self.state_dir, exist_ok=True)

    def write_state_files(self, session_id: str, token: Optional[str] = None) -> dict:
        """Write both state files atomically."""
        logger.info("Writing state files", extra={
            'tool_name': 'StateWriter',
            'session_id': session_id,
            'has_token': token is not None
        })

        result = {
            'verifier_loop_path': None,
            'token_secret_path': None,
            'success': False
        }

        try:
            result['verifier_loop_path'] = self.write_verifier_loop(session_id)
            if token:
                result['token_secret_path'] = self.write_token_secret(session_id, token)
            result['success'] = True
            logger.info("State files written successfully", extra={
                'tool_name': 'StateWriter',
                'session_id': session_id,
            })
        except Exception as e:
            logger.error(f"Failed to write state files: {e}", extra={
                'tool_name': 'StateWriter',
                'session_id': session_id
            })
            raise RuntimeError(f"Failed to write state files: {e}")

        return result

    def write_verifier_loop(self, session_id: str) -> str:
        """Write verifier-loop.local.md atomically."""
        session_row = self.db.fetchone(
            'SELECT * FROM sessions WHERE session_id = ?',
            (session_id,)
        )

        if not session_row:
            raise ValueError(f"Session '{session_id}' not found")

        try:
            iteration = session_row['iteration'] if session_row['iteration'] is not None else 1
        except (KeyError, TypeError):
            iteration = 1

        try:
            max_iterations = session_row['max_iterations'] if session_row['max_iterations'] is not None else 10
        except (KeyError, TypeError):
            max_iterations = 10

        try:
            task_id = session_row['task_id'] if session_row['task_id'] is not None else ''
        except (KeyError, TypeError):
            task_id = ''

        try:
            project_dir = session_row['project_dir'] if session_row['project_dir'] is not None else self.project_dir
        except (KeyError, TypeError):
            project_dir = self.project_dir

        try:
            test_command = session_row['test_command'] if session_row['test_command'] is not None else 'pytest tests/'
        except (KeyError, TypeError):
            test_command = 'pytest tests/'

        try:
            plan_mode = bool(session_row['plan_mode']) if session_row['plan_mode'] is not None else False
        except (KeyError, TypeError):
            plan_mode = False

        context = {
            'session_id': session_row['session_id'],
            'iteration': iteration,
            'max_iterations': max_iterations,
            'started_at': session_row['started_at'],
            'task_id': task_id,
            'project_dir': project_dir,
            'test_command': test_command,
            'plan_mode': plan_mode
        }

        template = get_template('verifier_loop.md.j2')
        content = template.render(**context)

        target_path = os.path.join(self.state_dir, 'verifier-loop.local.md')
        self._atomic_write(target_path, content)

        return target_path

    def write_token_secret(self, session_id: str, token: str) -> str:
        """Write verifier-token.secret atomically."""
        session_row = self.db.fetchone(
            'SELECT test_command FROM sessions WHERE session_id = ?',
            (session_id,)
        )

        test_command = 'pytest tests/'
        if session_row and session_row['test_command']:
            test_command = session_row['test_command']

        test_cmd_b64 = base64.b64encode(test_command.encode()).decode()
        test_cmd_hash = hashlib.sha256(test_command.encode()).hexdigest()

        context = {
            'token': token,
            'test_cmd_b64': test_cmd_b64,
            'test_cmd_hash': test_cmd_hash
        }

        template = get_template('token_secret.j2')
        content = template.render(**context)

        target_path = os.path.join(self.state_dir, 'verifier-token.secret')
        self._atomic_write(target_path, content)

        return target_path

    def _atomic_write(self, target_path: str, content: str) -> None:
        """Write content to target_path atomically."""
        target_dir = os.path.dirname(target_path)
        fd, temp_path = tempfile.mkstemp(dir=target_dir, suffix='.tmp')

        try:
            with os.fdopen(fd, 'w') as f:
                f.write(content)
            os.rename(temp_path, target_path)
        except Exception as e:
            try:
                os.unlink(temp_path)
            except:
                pass
            raise RuntimeError(f"Atomic write failed: {e}")
