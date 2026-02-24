"""
FastMCP server for Gatekeeper centralized token management.

This server provides MCP tools for:
- Session lifecycle management (create, get, close)
- Token submission and validation (completion, phase gate, test quality)
- Agent signal recording and processing
- Evolution attempt tracking
- Usage metrics collection

Usage:
    python3 -m gatekeeper_mcp.server_v3
"""

import logging
from typing import Dict, Any
from fastmcp import FastMCP

from gatekeeper_mcp.config import Config
from gatekeeper_mcp.logging_config import setup_logging
from gatekeeper_mcp.database import DatabaseManager
from gatekeeper_mcp.state_writer import StateWriter

# Initialize logger (will be configured in main())
logger = logging.getLogger(__name__)

# Global instances (initialized in main())
config: Config = None
db: DatabaseManager = None
state_writer: StateWriter = None

# Create FastMCP server
mcp = FastMCP("gatekeeper-mcp")


def health_check() -> Dict[str, Any]:
    """
    Check server health and database connectivity.

    Returns:
        Dict with status, db_connected, and version fields

    Example:
        result = await health_check()
        # Returns: {"status": "ok", "db_connected": true, "version": "1.0"}
    """
    logger.info("Health check requested", extra={'tool_name': 'health_check'})

    db_connected = False
    try:
        # Test database connection by querying schema version
        if db:
            row = db.fetchone("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
            db_connected = row is not None
    except Exception as e:
        logger.error(f"Database connection failed: {e}", extra={'tool_name': 'health_check'})

    return {
        "status": "ok",
        "db_connected": db_connected,
        "version": "1.0"
    }


# Register the tool with FastMCP
mcp.tool(health_check)


def initialize_server() -> None:
    """
    Initialize server components: configuration, logging, database, tools.

    This function:
    1. Loads configuration from environment
    2. Sets up structured logging
    3. Initializes database with schema
    4. Ensures required directories exist
    5. Creates StateWriter instance
    6. Registers MCP tools
    """
    global config, db, state_writer

    # Load configuration
    config = Config.from_env()

    # Setup structured logging
    setup_logging(config.log_level)
    logger.info("Configuration loaded", extra={
        'tool_name': 'server',
        'db_path': config.db_path,
        'session_dir': config.session_dir,
        'log_level': config.log_level
    })

    # Ensure directories exist
    config.ensure_directories()
    logger.info("Directories ensured", extra={'tool_name': 'server'})

    # Initialize database (schema applied automatically if not exists)
    db = DatabaseManager(config.db_path)
    logger.info("Database initialized", extra={'tool_name': 'server', 'db_path': config.db_path})

    # Initialize state writer
    state_writer = StateWriter(config.session_dir, db)
    logger.info("State writer initialized", extra={'tool_name': 'server'})

    # Register session tools
    from gatekeeper_mcp.tools import sessions
    from gatekeeper_mcp.tools import tokens
    from gatekeeper_mcp.tools import signals
    from gatekeeper_mcp.tools import phase_gates
    from gatekeeper_mcp.tools import evolution
    sessions.register_tools(mcp, db)
    logger.info("Session tools registered", extra={'tool_name': 'server'})

    # Register token tools
    tokens.register_tools(mcp, db, state_writer)
    logger.info("Token tools registered", extra={'tool_name': 'server'})

    # Register signal tools
    signals.register_tools(mcp, db, state_writer)
    logger.info("Signal tools registered", extra={'tool_name': 'server'})

    # Register phase gate tools
    phase_gates.register_tools(mcp, db, state_writer)
    logger.info("Phase gate tools registered", extra={'tool_name': 'server'})

    # Register evolution tools
    evolution.register_tools(mcp, db, state_writer)
    logger.info("Evolution tools registered", extra={'tool_name': 'server'})


def main() -> None:
    """
    Main entry point for the MCP server.

    Initializes server components and starts the FastMCP server.
    """
    # Initialize all components
    initialize_server()

    # Log server startup
    logger.info("Starting Gatekeeper MCP server", extra={'tool_name': 'server'})

    # Start FastMCP server
    mcp.run()


if __name__ == '__main__':
    main()
