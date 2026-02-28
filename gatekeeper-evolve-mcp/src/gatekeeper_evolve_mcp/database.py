"""
Database connection pooling and query utilities for Gatekeeper Evolve MCP.

Provides DatabaseManager class with:
- Connection pooling via sqlite3
- Parameterized query execution (SQL injection prevention)
- Context manager support for automatic connection cleanup
- Schema initialization from unified_schema.sql
"""

import sqlite3
from pathlib import Path
from typing import Optional, List, Any, Dict
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages SQLite database connections and queries."""

    def __init__(self, db_path: str, schema_path: Optional[str] = None):
        """
        Initialize database manager.

        Args:
            db_path: Path to SQLite database file
            schema_path: Path to schema SQL file (default: unified_schema.sql)
        """
        self.db_path = db_path
        if schema_path is None:
            module_dir = Path(__file__).parent  # src/gatekeeper_evolve_mcp
            gatekeeper_dir = module_dir.parent.parent  # gatekeeper-evolve-mcp
            schema_path = str(gatekeeper_dir / 'unified_schema.sql')
        self.schema_path = schema_path
        self._connection: Optional[sqlite3.Connection] = None

        if not Path(db_path).exists():
            self._initialize_database()

    def _initialize_database(self) -> None:
        """Create database and apply schema."""
        logger.info(f"Initializing database at {self.db_path}")

        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with open(self.schema_path, 'r') as f:
            schema_sql = f.read()

        conn = self._get_connection()
        try:
            conn.executescript(schema_sql)
            conn.commit()
            logger.info("Database schema initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database schema: {e}")
            raise
        finally:
            conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Create a new database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        return conn

    @contextmanager
    def connection(self):
        """Context manager for database connections."""
        conn = self._get_connection()
        try:
            yield conn
        finally:
            conn.close()

    def execute(self, conn: sqlite3.Connection, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a parameterized query."""
        logger.debug(f"Executing query: {query[:100]}... with params: {params}")
        return conn.execute(query, params)

    def fetchone(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """Execute query and fetch one result."""
        with self.connection() as conn:
            cursor = self.execute(conn, query, params)
            return cursor.fetchone()

    def fetchall(self, query: str, params: tuple = ()) -> List[sqlite3.Row]:
        """Execute query and fetch all results."""
        with self.connection() as conn:
            cursor = self.execute(conn, query, params)
            return cursor.fetchall()

    def insert(self, table: str, data: Dict[str, Any]) -> int:
        """Insert a row into a table. Returns row ID of inserted row."""
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])
        query = f'INSERT INTO {table} ({columns}) VALUES ({placeholders})'

        with self.connection() as conn:
            cursor = self.execute(conn, query, tuple(data.values()))
            conn.commit()
            return cursor.lastrowid

    def update(self, table: str, data: Dict[str, Any], where: str, where_params: tuple = ()) -> int:
        """Update rows in a table. Returns number of rows updated."""
        set_clause = ', '.join([f'{k} = ?' for k in data.keys()])
        query = f'UPDATE {table} SET {set_clause} WHERE {where}'

        with self.connection() as conn:
            cursor = self.execute(conn, query, tuple(data.values()) + where_params)
            conn.commit()
            return cursor.rowcount

    def delete(self, table: str, where: str, where_params: tuple = ()) -> int:
        """Delete rows from a table. Returns number of rows deleted."""
        query = f'DELETE FROM {table} WHERE {where}'

        with self.connection() as conn:
            cursor = self.execute(conn, query, where_params)
            conn.commit()
            return cursor.rowcount

    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        with self.connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Transaction rolled back: {e}")
                raise
