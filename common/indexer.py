import sqlite3
import logging
import os
from pathlib import Path
from typing import List


def initialize_database(
    db_dir: str = ".", db_name: str = "filesystem_index.db"
) -> sqlite3.Connection:
    """Initializes the SQLite database and creates tables if they don't exist.

    Args:
        db_dir (str): Directory to store the database file.
        db_name (str): Name of the database file.

    Returns:
        sqlite3.Connection: SQLite database connection.
    """
    db_path = os.path.join(db_dir, db_name)
    conn = sqlite3.connect(db_path)
    create_tables(conn)
    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    """Creates necessary tables in the database.

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


def update_index_after_change(
    conn: sqlite3.Connection, action: str, path: Path
) -> None:
    """Updates the index after files/directories are changed.

    Args:
        conn (sqlite3.Connection): SQLite database connection.
        action (str): The action performed ('delete_file', 'delete_directory', 'add_file', 'add_directory').
        path (Path): Path of the file or directory affected.
    """
    cursor = conn.cursor()
    if action == "delete_file":
        cursor.execute(
            "DELETE FROM files WHERE directory_path = ? AND name = ?",
            (str(path.parent), path.name),
        )
    elif action == "delete_directory":
        # Delete directory entry and all files under it
        cursor.execute("DELETE FROM directories WHERE path = ?", (str(path),))
        cursor.execute("DELETE FROM files WHERE directory_path = ?", (str(path),))
        # Optionally, delete subdirectories recursively if they were indexed
        cursor.execute(
            "DELETE FROM directories WHERE parent_path LIKE ?", (str(path) + "%",)
        )
        cursor.execute(
            "DELETE FROM files WHERE directory_path LIKE ?", (str(path) + "%",)
        )
    elif action == "add_file":
        mtime = path.stat().st_mtime
        size = path.stat().st_size
        cursor.execute(
            "INSERT OR IGNORE INTO files (directory_path, name, size, mtime) VALUES (?, ?, ?, ?)",
            (str(path.parent), path.name, size, mtime),
        )
    elif action == "add_directory":
        mtime = path.stat().st_mtime
        parent_path = str(path.parent)
        cursor.execute(
            "INSERT OR IGNORE INTO directories (path, parent_path, mtime) VALUES (?, ?, ?)",
            (str(path), parent_path, mtime),
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
    directories = [Path(row[0]) for row in cursor.fetchall()]
    return directories


def close_database(conn: sqlite3.Connection) -> None:
    """Closes the database connection.

    Args:
        conn (sqlite3.Connection): SQLite database connection.
    """
    conn.close()
    logging.info({"action": "database_closed"})
