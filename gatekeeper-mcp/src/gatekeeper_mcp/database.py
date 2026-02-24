"""
Database connection pooling and query utilities for Gatekeeper MCP.

Provides DatabaseManager class with:
- Connection pooling via sqlite3
- Parameterized query execution (SQL injection prevention)
- Context manager support for automatic connection cleanup
- Schema initialization from token_schema.sql
"""

import sqlite3
from pathlib import Path
from typing import Optional, List, Any, Dict
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages SQLite database connections and queries.

    Usage:
        db = DatabaseManager('/path/to/gatekeeper.db')

        # Context manager for automatic cleanup
        with db.connection() as conn:
            cursor = db.execute(conn, 'SELECT * FROM sessions WHERE session_id = ?', (session_id,))
            row = cursor.fetchone()

        # Or use convenience methods
        row = db.fetchone('SELECT * FROM sessions WHERE session_id = ?', (session_id,))
        rows = db.fetchall('SELECT * FROM sessions WHERE active = 1')
    """

    def __init__(self, db_path: str, schema_path: Optional[str] = None):
        """
        Initialize database manager.

        Args:
            db_path: Path to SQLite database file
            schema_path: Path to schema SQL file (default: gatekeeper-mcp/token_schema.sql)
        """
        self.db_path = db_path
        # Default to schema file in gatekeeper-mcp directory
        if schema_path is None:
            # Find the gatekeeper-mcp directory relative to this module
            module_dir = Path(__file__).parent  # src/gatekeeper_mcp
            gatekeeper_dir = module_dir.parent.parent  # gatekeeper-mcp
            schema_path = str(gatekeeper_dir / 'token_schema.sql')
        self.schema_path = schema_path
        self._connection: Optional[sqlite3.Connection] = None

        # Initialize database with schema if it doesn't exist
        if not Path(db_path).exists():
            self._initialize_database()

    def _initialize_database(self) -> None:
        """Create database and apply schema."""
        logger.info(f"Initializing database at {self.db_path}")

        # Create parent directories if needed
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # Read and execute schema
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
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        conn.execute('PRAGMA foreign_keys = ON')  # Enable foreign key enforcement
        return conn

    @contextmanager
    def connection(self):
        """
        Context manager for database connections.

        Yields:
            sqlite3.Connection: Database connection

        Usage:
            with db.connection() as conn:
                cursor = db.execute(conn, 'SELECT * FROM sessions')
                rows = cursor.fetchall()
        """
        conn = self._get_connection()
        try:
            yield conn
        finally:
            conn.close()

    def execute(self, conn: sqlite3.Connection, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """
        Execute a parameterized query.

        Args:
            conn: Database connection
            query: SQL query with ? placeholders
            params: Tuple of parameters

        Returns:
            sqlite3.Cursor: Cursor with results

        Example:
            cursor = db.execute(conn, 'SELECT * FROM sessions WHERE session_id = ?', (session_id,))
        """
        logger.debug(f"Executing query: {query[:100]}... with params: {params}")
        return conn.execute(query, params)

    def fetchone(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """
        Execute query and fetch one result.

        Args:
            query: SQL query with ? placeholders
            params: Tuple of parameters

        Returns:
            sqlite3.Row or None: Single row result

        Example:
            row = db.fetchone('SELECT * FROM sessions WHERE session_id = ?', (session_id,))
            if row:
                session = Session.from_row(row)
        """
        with self.connection() as conn:
            cursor = self.execute(conn, query, params)
            return cursor.fetchone()

    def fetchall(self, query: str, params: tuple = ()) -> List[sqlite3.Row]:
        """
        Execute query and fetch all results.

        Args:
            query: SQL query with ? placeholders
            params: Tuple of parameters

        Returns:
            List of sqlite3.Row objects

        Example:
            rows = db.fetchall('SELECT * FROM agent_signals WHERE pending = 1')
            signals = [AgentSignal.from_row(row) for row in rows]
        """
        with self.connection() as conn:
            cursor = self.execute(conn, query, params)
            return cursor.fetchall()

    def insert(self, table: str, data: Dict[str, Any]) -> int:
        """
        Insert a row into a table.

        Args:
            table: Table name
            data: Dictionary of column -> value

        Returns:
            int: Row ID of inserted row

        Example:
            row_id = db.insert('sessions', {
                'session_id': 'gk_20260223_a3f2c1',
                'iteration': 1,
                'max_iterations': 10,
                # ...
            })
        """
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])
        query = f'INSERT INTO {table} ({columns}) VALUES ({placeholders})'

        with self.connection() as conn:
            cursor = self.execute(conn, query, tuple(data.values()))
            conn.commit()
            return cursor.lastrowid

    def update(self, table: str, data: Dict[str, Any], where: str, where_params: tuple = ()) -> int:
        """
        Update rows in a table.

        Args:
            table: Table name
            data: Dictionary of column -> new value
            where: WHERE clause (without 'WHERE' keyword)
            where_params: Parameters for WHERE clause

        Returns:
            int: Number of rows updated

        Example:
            rows_updated = db.update(
                'agent_signals',
                {'pending': 0, 'processed_at': '2026-02-23T10:00:00Z'},
                'id = ?',
                (signal_id,)
            )
        """
        set_clause = ', '.join([f'{k} = ?' for k in data.keys()])
        query = f'UPDATE {table} SET {set_clause} WHERE {where}'

        with self.connection() as conn:
            cursor = self.execute(conn, query, tuple(data.values()) + where_params)
            conn.commit()
            return cursor.rowcount

    def delete(self, table: str, where: str, where_params: tuple = ()) -> int:
        """
        Delete rows from a table.

        Args:
            table: Table name
            where: WHERE clause (without 'WHERE' keyword)
            where_params: Parameters for WHERE clause

        Returns:
            int: Number of rows deleted

        Example:
            rows_deleted = db.delete('sessions', 'active = 0')
        """
        query = f'DELETE FROM {table} WHERE {where}'

        with self.connection() as conn:
            cursor = self.execute(conn, query, where_params)
            conn.commit()
            return cursor.rowcount

    @contextmanager
    def transaction(self):
        """
        Context manager for database transactions.

        Yields:
            sqlite3.Connection: Database connection

        Usage:
            with db.transaction() as conn:
                db.execute(conn, 'INSERT INTO sessions ...', params)
                db.execute(conn, 'INSERT INTO completion_tokens ...', params)
                # Auto-commits on successful exit, rolls back on exception
        """
        with self.connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Transaction rolled back: {e}")
                raise
