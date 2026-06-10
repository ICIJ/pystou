import sqlite3
import logging
import os
from pathlib import Path
from typing import List

from common.errors import PystouError


def initialize_database(
    db_dir: str = ".", db_name: str = "filesystem_index.db"
) -> sqlite3.Connection:
    """Initializes the SQLite database and creates tables if they don't exist.

    Args:
        db_dir (str): Directory to store the database file.
        db_name (str): Name of the database file.

    Returns:
        sqlite3.Connection: SQLite database connection.

    Raises:
        PystouError: If the database file cannot be opened.
    """
    db_path = os.path.join(db_dir, db_name)
    try:
        conn = sqlite3.connect(db_path)
        create_tables(conn)
    except sqlite3.Error as e:
        raise PystouError(f"Could not open index database at {db_path}: {e}")
    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    """Creates necessary tables and indexes in the database.

    Args:
        conn (sqlite3.Connection): SQLite database connection.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS directories (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE,
            parent_path TEXT,
            mtime REAL
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            directory_path TEXT,
            name TEXT,
            size INTEGER,
            mtime REAL
        )
    """
    )
    # Create indexes for faster queries
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_directories_parent ON directories(parent_path)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_files_directory ON files(directory_path)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_files_name ON files(name)"
    )
    conn.commit()


def prompt_use_existing_index() -> bool:
    """Prompts the user to decide whether to use the existing index.

    Returns:
        bool: True if the user wants to use the existing index, False otherwise.
    """
    while True:
        choice = (
            input(
                "An index file was found. Do you want to use the existing index? (Y/n): "
            )
            .strip()
            .lower()
        )
        if choice in {"y", "yes", ""}:
            return True
        elif choice in {"n", "no"}:
            return False
        print("Invalid input. Please enter 'Y' or 'n'.")


def _escape_like(text: str) -> str:
    """Escapes SQL LIKE wildcards so paths match literally (ESCAPE '\\')."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def update_index_after_change(
    conn: sqlite3.Connection, action: str, path: Path
) -> None:
    """Updates the index after files/directories are changed.

    Args:
        conn (sqlite3.Connection): SQLite database connection.
        action (str): One of 'delete_file', 'delete_directory', 'add_file',
            'add_directory'.
        path (Path): Path of the file or directory affected.
    """
    cursor = conn.cursor()
    if action == "delete_file":
        cursor.execute(
            "DELETE FROM files WHERE directory_path = ? AND name = ?",
            (str(path.parent), path.name),
        )
    elif action == "delete_directory":
        path_str = str(path)
        # Match the directory itself and only true descendants (path + separator),
        # escaping LIKE wildcards so '%'/'_' in real paths are treated literally.
        descendant = _escape_like(path_str + os.sep) + "%"
        cursor.execute(
            "DELETE FROM directories WHERE path = ? OR path LIKE ? ESCAPE '\\'",
            (path_str, descendant),
        )
        cursor.execute(
            "DELETE FROM files WHERE directory_path = ? OR directory_path LIKE ? ESCAPE '\\'",
            (path_str, descendant),
        )
    elif action == "add_file":
        try:
            stat_info = path.stat()
        except OSError:
            logging.warning(
                {"action": "index_add_file", "status": "stat_failed", "path": str(path)}
            )
            return
        cursor.execute(
            "INSERT OR IGNORE INTO files (directory_path, name, size, mtime) VALUES (?, ?, ?, ?)",
            (str(path.parent), path.name, stat_info.st_size, stat_info.st_mtime),
        )
    elif action == "add_directory":
        try:
            stat_info = path.stat()
        except OSError:
            logging.warning(
                {"action": "index_add_directory", "status": "stat_failed", "path": str(path)}
            )
            return
        cursor.execute(
            "INSERT OR IGNORE INTO directories (path, parent_path, mtime) VALUES (?, ?, ?)",
            (str(path), str(path.parent), stat_info.st_mtime),
        )
    conn.commit()


def load_directories_from_index(conn: sqlite3.Connection) -> List[Path]:
    """Loads directory paths from the database.

    Args:
        conn (sqlite3.Connection): SQLite database connection.

    Returns:
        List[Path]: List of directory paths.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT path FROM directories")
    # Iterate over cursor directly for better memory efficiency
    directories = [Path(row[0]) for row in cursor]
    return directories


def close_database(conn: sqlite3.Connection) -> None:
    """Closes the database connection.

    Args:
        conn (sqlite3.Connection): SQLite database connection.
    """
    conn.close()
    logging.info({"action": "database_closed"})
