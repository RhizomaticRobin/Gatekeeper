"""
Unified FastMCP server for Gatekeeper Evolve — merged gatekeeper-mcp + evolve-mcp.

This server provides MCP tools for:
- Session lifecycle management (create, get, close)
- Token submission and validation (completion, phase gate, test quality)
- Agent signal recording and processing
- Evolution attempt tracking (unified approaches table)
- Usage metrics collection
- MAP-Elites population operations
- Cascade evaluation with timing
- Profiling, function extraction/mutation
- Taichi GPU kernel profiling/analysis/harness-generation
- Novelty checking

Usage:
    python3 -m gatekeeper_evolve_mcp
"""

import logging
from typing import Dict, Any
from fastmcp import FastMCP

from gatekeeper_evolve_mcp.config import Config
from gatekeeper_evolve_mcp.logging_config import setup_logging
from gatekeeper_evolve_mcp.database import DatabaseManager
from gatekeeper_evolve_mcp.state_writer import StateWriter
from gatekeeper_evolve_mcp import evolve_runner

logger = logging.getLogger(__name__)

# Global instances (initialized in main())
config: Config = None
db: DatabaseManager = None
state_writer: StateWriter = None

# Create FastMCP server
mcp = FastMCP("gatekeeper-evolve-mcp")


def health_check() -> Dict[str, Any]:
    """Check server health and database connectivity."""
    db_connected = False
    try:
        if db:
            row = db.fetchone("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
            db_connected = row is not None
    except Exception as e:
        logger.error(f"Database connection failed: {e}", extra={'tool_name': 'health_check'})

    return {
        "status": "ok",
        "db_connected": db_connected,
        "version": "2.0"
    }


mcp.tool(health_check)


def _apply_verification_migration(db_instance: DatabaseManager) -> None:
    """Apply verification_results migration if the table doesn't exist."""
    try:
        row = db_instance.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='verification_results'"
        )
        if row is None:
            from pathlib import Path
            migration_path = Path(__file__).parent.parent.parent / 'verification_migration.sql'
            if migration_path.exists():
                migration_sql = migration_path.read_text()
                with db_instance.connection() as conn:
                    conn.executescript(migration_sql)
                logger.info("Applied verification_results migration", extra={'tool_name': 'server'})
            else:
                logger.warning(f"Migration file not found: {migration_path}", extra={'tool_name': 'server'})
    except Exception as e:
        logger.error(f"Failed to apply verification migration: {e}", extra={'tool_name': 'server'})


def initialize_server() -> None:
    """
    Initialize server components: configuration, logging, database, tools.

    This function:
    1. Loads configuration from environment
    2. Sets up structured logging
    3. Initializes database with unified schema
    4. Ensures required directories exist
    5. Creates StateWriter instance
    6. Configures evolve_runner with database path
    7. Registers all MCP tools (gatekeeper + evolve)
    """
    global config, db, state_writer

    config = Config.from_env()

    setup_logging(config.log_level)
    logger.info("Configuration loaded", extra={
        'tool_name': 'server',
        'db_path': config.db_path,
        'session_dir': config.session_dir,
        'log_level': config.log_level
    })

    config.ensure_directories()

    db = DatabaseManager(config.db_path)
    logger.info("Database initialized", extra={'tool_name': 'server', 'db_path': config.db_path})

    # Auto-migrate: add verification_results table if missing
    _apply_verification_migration(db)

    state_writer = StateWriter(config.session_dir, db)
    logger.info("State writer initialized", extra={'tool_name': 'server'})

    # Configure evolve_runner with database path for subprocess env injection
    evolve_runner.set_db_path(config.db_path)

    # Register gatekeeper tools
    from gatekeeper_evolve_mcp.tools import sessions
    from gatekeeper_evolve_mcp.tools import tokens
    from gatekeeper_evolve_mcp.tools import signals
    from gatekeeper_evolve_mcp.tools import phase_gates
    from gatekeeper_evolve_mcp.tools import evolution
    from gatekeeper_evolve_mcp.tools import usage
    from gatekeeper_evolve_mcp.tools import evolve

    sessions.register_tools(mcp, db)
    logger.info("Session tools registered", extra={'tool_name': 'server'})

    tokens.register_tools(mcp, db, state_writer)
    logger.info("Token tools registered", extra={'tool_name': 'server'})

    signals.register_tools(mcp, db, state_writer)
    logger.info("Signal tools registered", extra={'tool_name': 'server'})

    phase_gates.register_tools(mcp, db, state_writer)
    logger.info("Phase gate tools registered", extra={'tool_name': 'server'})

    from gatekeeper_evolve_mcp.tools import task_encryption
    task_encryption.register_tools(mcp, db, state_writer)
    logger.info("Task encryption tools registered", extra={'tool_name': 'server'})

    evolution.register_tools(mcp, db, state_writer)
    logger.info("Evolution tools registered", extra={'tool_name': 'server'})

    usage.register_tools(mcp, db)
    logger.info("Usage tools registered", extra={'tool_name': 'server'})

    # Register evolve tools (MAP-Elites, evaluation, profiling, extraction, GPU)
    evolve.register_tools(mcp, db)
    logger.info("Evolve tools registered", extra={'tool_name': 'server'})

    # Register formal verification tools (ERMACK v2)
    from gatekeeper_evolve_mcp.tools import prusti
    from gatekeeper_evolve_mcp.tools import kani
    from gatekeeper_evolve_mcp.tools import semver
    from gatekeeper_evolve_mcp.tools import python_contracts
    from gatekeeper_evolve_mcp.tools import composability
    from gatekeeper_evolve_mcp.tools import verification_orchestrator

    prusti.register_tools(mcp, db)
    logger.info("Prusti verification tools registered", extra={'tool_name': 'server'})

    kani.register_tools(mcp, db)
    logger.info("Kani verification tools registered", extra={'tool_name': 'server'})

    semver.register_tools(mcp, db)
    logger.info("Semver compatibility tools registered", extra={'tool_name': 'server'})

    python_contracts.register_tools(mcp, db)
    logger.info("Python contracts tools registered", extra={'tool_name': 'server'})

    composability.register_tools(mcp, db)
    logger.info("Composability tools registered", extra={'tool_name': 'server'})

    verification_orchestrator.register_tools(mcp, db)
    logger.info("Verification orchestrator tools registered", extra={'tool_name': 'server'})


def main() -> None:
    """Main entry point for the MCP server."""
    initialize_server()
    logger.info("Starting Gatekeeper Evolve MCP server", extra={'tool_name': 'server'})
    mcp.run()


if __name__ == '__main__':
    main()
