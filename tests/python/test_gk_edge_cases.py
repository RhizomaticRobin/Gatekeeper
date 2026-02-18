"""Tests for Gatekeeper edge case hardening.

Covers:
- Token file permissions (chmod 600)
- State file started_at timestamp in frontmatter
- Stale session detection (>24h)
"""

import os
import stat
import subprocess
import tempfile
import re
from datetime import datetime, timezone, timedelta


PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SETUP_SCRIPT = os.path.join(PLUGIN_ROOT, 'scripts', 'setup-verifier-loop.sh')


def _run_setup(tmp_dir, extra_args=None):
    """Run setup-verifier-loop.sh in a temp directory and return the result."""
    cmd = [
        'bash', SETUP_SCRIPT,
        '--verification-criteria', 'test criteria',
        '--test-command', 'echo pass',
        'test prompt',
    ]
    if extra_args:
        cmd = ['bash', SETUP_SCRIPT] + extra_args
    env = os.environ.copy()
    result = subprocess.run(
        cmd,
        cwd=tmp_dir,
        capture_output=True,
        text=True,
        env=env,
    )
    return result


class TestTokenFilePermissions:
    """Verify that verifier-token.secret gets chmod 600 after creation."""

    def test_token_file_permissions(self, tmp_path):
        """Token file should have 600 permissions (owner read/write only)."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir()

        result = _run_setup(str(tmp_path))
        assert result.returncode == 0, f"Setup failed: {result.stderr}"

        token_file = claude_dir / 'verifier-token.secret'
        assert token_file.exists(), "Token file was not created"

        file_stat = os.stat(str(token_file))
        permissions = stat.S_IMODE(file_stat.st_mode)
        assert permissions == 0o600, (
            f"Token file permissions should be 0600, got {oct(permissions)}"
        )


class TestStateFileTimestamp:
    """Verify that verifier-loop.local.md contains started_at timestamp."""

    def test_state_file_has_timestamp(self, tmp_path):
        """State file frontmatter should contain started_at in ISO 8601 format."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir()

        result = _run_setup(str(tmp_path))
        assert result.returncode == 0, f"Setup failed: {result.stderr}"

        state_file = claude_dir / 'verifier-loop.local.md'
        assert state_file.exists(), "State file was not created"

        content = state_file.read_text()

        # Extract frontmatter (between --- markers)
        frontmatter_match = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
        assert frontmatter_match, "No frontmatter found in state file"
        frontmatter = frontmatter_match.group(1)

        # Check started_at field exists
        started_at_match = re.search(r'started_at:\s*"([^"]+)"', frontmatter)
        assert started_at_match, (
            f"started_at not found in frontmatter:\n{frontmatter}"
        )

        # Validate ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)
        timestamp_str = started_at_match.group(1)
        try:
            parsed = datetime.strptime(timestamp_str, '%Y-%m-%dT%H:%M:%SZ')
        except ValueError:
            raise AssertionError(
                f"started_at '{timestamp_str}' is not valid ISO 8601 format"
            )

        # Should be within the last 60 seconds (accounting for test execution time)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        delta = abs((now - parsed).total_seconds())
        assert delta < 60, (
            f"started_at timestamp is {delta}s away from now, expected <60s"
        )


class TestStaleDetectionLogic:
    """Verify stale session detection: sessions older than 24h are flagged."""

    def test_stale_detection_logic(self, tmp_path):
        """A session with started_at >24h ago should be detected as stale by stop-hook."""
        claude_dir = tmp_path / '.claude'
        claude_dir.mkdir()

        # Create a state file with started_at 25 hours ago
        stale_time = datetime.now(timezone.utc) - timedelta(hours=25)
        stale_timestamp = stale_time.strftime('%Y-%m-%dT%H:%M:%SZ')

        token = "GK_COMPLETE_0000000000000000ab54a98ceb1f0ad2"

        state_content = f"""---
active: true
session_id: "stale-session-001"
iteration: 1
max_iterations: 5
verification_criteria: |
  test criteria
test_command: "echo pass"
verifier_model: "opus"
project_dir: "{tmp_path}"
started_at: "{stale_timestamp}"
---

Test prompt for stale session.
"""
        (claude_dir / 'verifier-loop.local.md').write_text(state_content)

        # Create a valid token file
        (claude_dir / 'verifier-token.secret').write_text(token + '\n')

        # Create a transcript without the token
        transcript = tmp_path / 'transcript.json'
        transcript.write_text('no token here')

        hook_script = os.path.join(PLUGIN_ROOT, 'hooks', 'stop-hook.sh')
        hook_input = f'{{"transcript_path": "{transcript}"}}'

        result = subprocess.run(
            ['bash', hook_script],
            input=hook_input,
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
        )

        # Stop hook should exit 0 (always graceful)
        assert result.returncode == 0, f"Stop hook failed: {result.stderr}"

        # Should warn about stale session in stderr
        assert 'stale' in result.stderr.lower() or 'expired' in result.stderr.lower(), (
            f"Expected stale/expired warning in stderr, got: {result.stderr}"
        )

        # Should clean up state files
        assert not (claude_dir / 'verifier-loop.local.md').exists(), (
            "State file should be cleaned up for stale sessions"
        )
