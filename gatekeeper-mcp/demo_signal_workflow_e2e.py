"""
End-to-end demo of signal workflow with multiple agents.

This demo shows:
1. Multiple agents recording signals
2. Orchestrator querying and processing signals
3. State file updates on completion signals
4. Realistic coordination pattern

Usage:
    python3 -m gatekeeper_mcp.demo_signal_workflow_e2e
"""

import sys
import os
import tempfile
import json
from datetime import datetime

sys.path.insert(0, '/workspace/craftium/gatekeeper-mcp/src')

from gatekeeper_mcp.database import DatabaseManager
from gatekeeper_mcp.state_writer import StateWriter
from gatekeeper_mcp.config import Config
from gatekeeper_mcp.logging_config import setup_logging
from gatekeeper_mcp.tools import sessions, tokens, signals


def main():
    """Run end-to-end signal workflow demo."""
    # Setup
    config = Config.from_env()
    setup_logging(config.log_level)

    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"Demo directory: {tmpdir}\n")

        # Initialize components
        db_path = os.path.join(tmpdir, "gatekeeper.db")
        db = DatabaseManager(db_path)
        state_writer = StateWriter(tmpdir, db)

        # Fake MCP
        class FakeMCP:
            def tool(self):
                return lambda f: f

        mcp = FakeMCP()

        # Register tools
        sessions.register_tools(mcp, db)
        tokens.register_tools(mcp, db, state_writer)
        signals.register_tools(mcp, db, state_writer)

        # Create session
        session_id = f"gk_{datetime.now().strftime('%Y%m%d_%H%M%S')}_e2e"
        print(f"=== Signal Workflow E2E Demo ===\n")
        print(f"1. Creating session: {session_id}")

        sessions.create_session(
            session_id=session_id,
            project_dir=tmpdir,
            test_command="pytest tests/",
            task_id="8.2",
            max_iterations=10,
            verifier_model="sonnet",
            plan_mode=False
        )

        # Submit a token (needed for state file writes)
        print(f"\n2. Submitting completion token...")
        token = "GK_COMPLETE_" + "a" * 32
        tokens.submit_token(
            token=token,
            session_id=session_id,
            task_id="8.2"
        )
        print(f"   Token submitted: {token[:20]}...")

        # Agent 1: Test writer records TESTS_WRITTEN
        print(f"\n3. Agent 1 (Test Writer) records TESTS_WRITTEN signal...")
        agent1_result = signals.record_agent_signal(
            signal_type="TESTS_WRITTEN",
            session_id=session_id,
            task_id="8.2",
            agent_id="test_writer_agent_001",
            context={
                "files": ["test_example.py", "test_another.py"],
                "tests_written": 15,
                "timestamp": datetime.now().isoformat()
            }
        )
        print(f"   Signal recorded: id={agent1_result['signal_id']}, pending={agent1_result['pending']}")

        # Agent 2: Verifier records VERIFICATION_PASS
        print(f"\n4. Agent 2 (Verifier) records VERIFICATION_PASS signal...")
        agent2_result = signals.record_agent_signal(
            signal_type="VERIFICATION_PASS",
            session_id=session_id,
            task_id="8.2",
            agent_id="verifier_agent_002",
            context={
                "tests_passed": 15,
                "tests_failed": 0,
                "coverage": "95%",
                "timestamp": datetime.now().isoformat()
            }
        )
        print(f"   Signal recorded: id={agent2_result['signal_id']}, pending={agent2_result['pending']}")

        # Agent 3: Different task signal
        print(f"\n5. Agent 3 (Executor) records IMPLEMENTATION_READY for task 8.3...")
        agent3_result = signals.record_agent_signal(
            signal_type="IMPLEMENTATION_READY",
            session_id=session_id,
            task_id="8.3",
            agent_id="executor_agent_003",
            context={"ready": True}
        )
        print(f"   Signal recorded: id={agent3_result['signal_id']}, pending={agent3_result['pending']}")

        # Orchestrator queries pending signals
        print(f"\n6. Orchestrator queries all pending signals...")
        pending = signals.get_pending_signals(session_id=session_id)
        print(f"   Found {pending['count']} pending signals:")
        for signal in pending['signals']:
            context_str = ""
            if signal['context_json']:
                context_data = json.loads(signal['context_json'])
                context_str = f", context keys: {list(context_data.keys())}"
            print(f"     - {signal['signal_type']} (agent={signal['agent_id']}, task={signal['task_id']}{context_str})")

        # Orchestrator filters signals
        print(f"\n7. Orchestrator filters signals by task_id='8.2'...")
        task_82_signals = signals.get_pending_signals(
            session_id=session_id,
            task_id="8.2"
        )
        print(f"   Found {task_82_signals['count']} signals for task 8.2")

        # Orchestrator processes signals
        print(f"\n8. Orchestrator processes signals...")
        for signal in pending['signals']:
            result = signals.mark_signal_processed(signal['id'])
            is_completion = signal['signal_type'] in ['VERIFICATION_PASS', 'ASSESSMENT_PASS',
                                                        'PHASE_ASSESSMENT_PASS', 'PHASE_VERIFICATION_PASS']
            print(f"   Processed: {signal['signal_type']} -> pending={result['pending']}, "
                  f"completion_signal={is_completion}")

        # Verify state files
        print(f"\n9. Verifying state files...")
        verifier_loop = os.path.join(tmpdir, '.claude', 'verifier-loop.local.md')
        if os.path.exists(verifier_loop):
            print(f"   verifier-loop.local.md exists")
            with open(verifier_loop) as f:
                content = f.read()
                if session_id in content:
                    print(f"   Session ID present in state file")
                if 'iteration:' in content:
                    print(f"   Iteration tracking present")
        else:
            print(f"   Note: verifier-loop.local.md may not exist if no completion signal was processed")

        # Query pending signals (should be empty)
        print(f"\n10. Verifying no pending signals remaining...")
        final_pending = signals.get_pending_signals(session_id=session_id)
        print(f"   Pending signals: {final_pending['count']}")

        # Show signal context preservation
        print(f"\n11. Demonstrating context preservation...")
        # Record new signal with complex context
        test_context = {
            "files": ["test_complex.py"],
            "metrics": {
                "coverage_percent": 98.5,
                "lines_covered": 450,
                "total_lines": 459
            },
            "timestamp": datetime.now().isoformat()
        }
        context_result = signals.record_agent_signal(
            signal_type="ASSESSMENT_PASS",
            session_id=session_id,
            task_id="8.4",
            context=test_context
        )
        print(f"   Recorded signal with complex context: id={context_result['signal_id']}")

        # Query back and verify
        query_result = signals.get_pending_signals(task_id="8.4")
        if query_result['count'] > 0:
            retrieved = query_result['signals'][0]
            retrieved_context = json.loads(retrieved['context_json'])
            print(f"   Context preserved: coverage={retrieved_context['metrics']['coverage_percent']}%")
            assert retrieved_context['metrics']['coverage_percent'] == 98.5
            print(f"   Context roundtrip successful")

        print(f"\n=== Demo Complete ===\n")


if __name__ == '__main__':
    main()
