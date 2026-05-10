"""SQLite database connection and helper functions."""

import os
import sqlite3
from contextlib import contextmanager

from config.settings import DATABASE_PATH

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def init_db():
    """Create all tables from schema.sql."""
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    with get_connection() as conn:
        with open(_SCHEMA_PATH, "r") as f:
            conn.executescript(f.read())


@contextmanager
def get_connection():
    """Yield a SQLite connection with row factory enabled."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_query(query, params=(), fetchone=False):
    """Execute a query and return results."""
    with get_connection() as conn:
        cursor = conn.execute(query, params)
        if fetchone:
            return cursor.fetchone()
        return cursor.fetchall()


def execute_insert(query, params=()):
    """Execute an insert and return the last row id."""
    with get_connection() as conn:
        cursor = conn.execute(query, params)
        return cursor.lastrowid


def execute_many(query, data):
    """Execute a query for multiple rows."""
    with get_connection() as conn:
        conn.executemany(query, data)
