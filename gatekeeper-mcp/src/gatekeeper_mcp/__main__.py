"""
Package entry point for running the MCP server.

Usage:
    python3 -m gatekeeper_mcp
    # Equivalent to: python3 -m gatekeeper_mcp.server_v3
"""

from gatekeeper_mcp.server_v3 import main

if __name__ == '__main__':
    main()
