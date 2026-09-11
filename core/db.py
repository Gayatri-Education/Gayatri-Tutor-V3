"""Gayatri AI — Safe Database Access.

Provides a safe way to get an SQLite connection, handling corrupt databases
by backing them up and creating a fresh one.
"""

import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("gayatri.db")

def get_safe_db_connection(db_path: Path | str) -> sqlite3.Connection:
    """Get a safe SQLite connection, handling corrupt databases by backing them up."""
    is_memory = str(db_path) == ":memory:"

    if not is_memory:
        db_path = Path(db_path)
        if db_path.exists() and db_path.stat().st_size > 0:
            try:
                conn = sqlite3.connect(str(db_path))
                try:
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA quick_check")
                    result = cursor.fetchone()
                    if not result or result[0] != "ok":
                        raise sqlite3.DatabaseError("PRAGMA quick_check failed")
                finally:
                    conn.close()
            except sqlite3.DatabaseError as e:
                logger.warning(f"Database {db_path} is corrupt: {e}. Backing up and recreating.")
                backup_path = db_path.with_name(f"{db_path.stem}.corrupt-{datetime.now().strftime('%Y%m%d-%H%M%S')}{db_path.suffix}")
                try:
                    shutil.move(str(db_path), str(backup_path))
                    logger.info(f"Corrupt database backed up to {backup_path}")
                except Exception as move_err:
                    logger.error(f"Failed to backup corrupt database: {move_err}")
                    try:
                        db_path.unlink(missing_ok=True)
                    except Exception as unlink_err:
                        logger.error(f"Failed to delete corrupt database: {unlink_err}")
                        raise sqlite3.DatabaseError(f"Database is corrupt and cannot be backed up or deleted: {unlink_err}")

        db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        if not is_memory:
            conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=10000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
    except Exception as exc:
        logger.warning(f"Could not apply database PRAGMAs: {exc}")
    return conn

