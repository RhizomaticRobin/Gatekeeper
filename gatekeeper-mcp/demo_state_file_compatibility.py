"""
Demo showing MCP-generated state files being read by stop-hook simulation.

Verifies backward compatibility with existing stop-hook.sh behavior.

Usage:
    python3 -m gatekeeper_mcp.demo_state_file_compatibility
"""

import sys
import os
import tempfile
import base64
import hashlib
import yaml
from datetime import datetime

sys.path.insert(0, '/workspace/craftium/gatekeeper-mcp/src')

from gatekeeper_mcp.database import DatabaseManager
from gatekeeper_mcp.state_writer import StateWriter
from gatekeeper_mcp.config import Config
from gatekeeper_mcp.logging_config import setup_logging
from gatekeeper_mcp.tools import sessions, tokens


def simulate_stop_hook_parsing(claude_dir):
    """Simulate stop-hook.sh parsing behavior."""
    verifier_loop = os.path.join(claude_dir, 'verifier-loop.local.md')
    token_secret = os.path.join(claude_dir, 'verifier-token.secret')

    print("\n=== Simulating stop-hook.sh Parsing ===\n")

    # Parse verifier-loop.local.md
    print("1. Parsing verifier-loop.local.md frontmatter...")
    with open(verifier_loop) as f:
        content = f.read()

    parts = content.split('---\n')
    frontmatter = yaml.safe_load(parts[1])

    print(f"   session_id: {frontmatter['session_id']}")
    print(f"   iteration: {frontmatter['iteration']}/{frontmatter['max_iterations']}")
    print(f"   task_id: {frontmatter['task_id']}")
    print(f"   test_command: {frontmatter['test_command']}")
    print(f"   plan_mode: {frontmatter['plan_mode']}")

    # Parse verifier-token.secret
    print("\n2. Parsing verifier-token.secret...")
    with open(token_secret) as f:
        lines = f.read().strip().split('\n')

    token = lines[0]
    b64_line = lines[1]
    hash_line = lines[2]

    b64_value = b64_line.split('=', 1)[1]
    hash_value = hash_line.split('=', 1)[1]

    print(f"   token: {token[:20]}...")
    print(f"   TEST_CMD_B64: {b64_value[:20]}...")

    # Validate integrity
    print("\n3. Validating token integrity...")
    decoded_cmd = base64.b64decode(b64_value).decode('utf-8')
    computed_hash = hashlib.sha256(decoded_cmd.encode('utf-8')).hexdigest()

    print(f"   Decoded test_command: {decoded_cmd}")
    print(f"   Computed SHA-256: {computed_hash[:20]}...")
    print(f"   Stored SHA-256: {hash_value[:20]}...")

    if computed_hash == hash_value:
        print("   PASS: Integrity check PASSED")
    else:
        print("   FAIL: Integrity check FAILED")
        return False

    # Check iteration
    print("\n4. Checking iteration limit...")
    if frontmatter['max_iterations'] > 0 and frontmatter['iteration'] >= frontmatter['max_iterations']:
        print(f"   PASS: Max iterations reached ({frontmatter['iteration']}/{frontmatter['max_iterations']})")
    else:
        print(f"   INFO: Continue loop ({frontmatter['iteration']}/{frontmatter['max_iterations']})")

    # Validate token format
    print("\n5. Validating token format...")
    import re
    if re.match(r'^GK_COMPLETE_[a-f0-9]{32}$', token):
        print(f"   PASS: Token format valid")
    else:
        print(f"   FAIL: Token format invalid")
        return False

    print("\n=== All Checks Passed ===\n")
    return True


def main():
    """Main demo function."""
    # Setup
    config = Config.from_env()
    setup_logging(config.log_level)

    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"Demo directory: {tmpdir}")

        # Initialize
        db_path = os.path.join(tmpdir, 'test_gatekeeper.db')
        db = DatabaseManager(db_path)
        state_writer = StateWriter(tmpdir, db)

        class FakeMCP:
            def tool(self):
                return lambda f: f

        mcp = FakeMCP()

        sessions.register_tools(mcp, db)
        tokens.register_tools(mcp, db, state_writer)

        # Create session
        session_id = f"gk_{datetime.now().strftime('%Y%m%d_%H%M%S')}_compat"
        print(f"\nCreating session: {session_id}")

        sessions.create_session(
            session_id=session_id,
            project_dir=tmpdir,
            test_command="pytest tests/ -v",
            task_id="8.3",
            max_iterations=10
        )

        # Submit token
        print(f"\nSubmitting token...")
        tokens.submit_token(
            token="GK_COMPLETE_" + "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
            session_id=session_id
        )

        # Simulate stop-hook
        claude_dir = os.path.join(tmpdir, '.claude')
        success = simulate_stop_hook_parsing(claude_dir)

        # Show state files
        print("\n=== State File Contents ===\n")

        verifier_loop = os.path.join(claude_dir, 'verifier-loop.local.md')
        print("verifier-loop.local.md:")
        print("-" * 60)
        with open(verifier_loop) as f:
            print(f.read())

        token_secret = os.path.join(claude_dir, 'verifier-token.secret')
        print("\nverifier-token.secret:")
        print("-" * 60)
        with open(token_secret) as f:
            print(f.read())

        print("\n=== Demo Complete ===\n")

        if success:
            print("SUCCESS: MCP state files are backward compatible with stop-hook.sh")
        else:
            print("FAILURE: Compatibility issues detected")

        return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
