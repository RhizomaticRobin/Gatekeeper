"""
Configuration management for Gatekeeper MCP server.

Loads settings from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    """
    Server configuration loaded from environment variables.

    Environment variables:
        GK_DB_PATH: Path to SQLite database file (default: /tmp/gatekeeper.db)
        GK_SESSION_DIR: Directory for session state files (default: /tmp/gatekeeper-sessions)
        GK_LOG_LEVEL: Logging level (default: INFO)
    """
    db_path: str
    session_dir: str
    log_level: str

    @classmethod
    def from_env(cls) -> 'Config':
        """
        Load configuration from environment variables.

        Returns:
            Config instance with environment values or defaults
        """
        db_path = os.getenv('GK_DB_PATH', '/tmp/gatekeeper.db')
        session_dir = os.getenv('GK_SESSION_DIR', '/tmp/gatekeeper-sessions')
        log_level = os.getenv('GK_LOG_LEVEL', 'INFO').upper()

        return cls(
            db_path=db_path,
            session_dir=session_dir,
            log_level=log_level
        )

    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.session_dir).mkdir(parents=True, exist_ok=True)
