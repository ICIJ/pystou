import hashlib
import logging
import os
import sqlite3
from pathlib import Path
from typing import Optional

from common import console, paths
from common.errors import PystouError
from common.fs_walker import collect_directories


def index_db_path(db_dir: Optional[str], directory: str) -> str:
    """Returns the index database file for a scan target.

    Each indexed tree gets its own database, keyed by the target's absolute
    path, so a run on one tree is never offered another tree's index.

    Args:
        db_dir (Optional[str]): Directory holding index databases. Defaults to
            the XDG index directory.
        directory (str): Directory being indexed.

    Returns:
        str: Path to the target's index database.
    """
    root = db_dir if db_dir else str(paths.index_dir())
    target = os.path.abspath(directory)
    digest = hashlib.sha256(os.fsencode(target)).hexdigest()[:12]
    return os.path.join(root, f"{os.path.basename(target) or 'root'}-{digest}.db")


def initialize_database(db_path: str) -> sqlite3.Connection:
    """Initializes the SQLite database and creates tables if they don't exist.

    Args:
        db_path (str): Path to the database file.

    Returns:
        sqlite3.Connection: SQLite database connection.

    Raises:
        PystouError: If the database file cannot be opened.
    """
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error as e:
        raise PystouError(f"Could not open index database at {db_path}: {e}") from e
    try:
        create_tables(conn)
    except sqlite3.Error as e:
        conn.close()
        raise PystouError(f"Could not open index database at {db_path}: {e}") from e
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
            mtime REAL,
            UNIQUE (directory_path, name)
        )
    """
    )
    unique_files = (
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_files_directory_name ON files(directory_path, name)"
    )
    try:
        cursor.execute(unique_files)
    except sqlite3.IntegrityError:
        cursor.execute(
            "DELETE FROM files WHERE id NOT IN"
            " (SELECT MIN(id) FROM files GROUP BY directory_path, name)"
        )
        cursor.execute(unique_files)
    # Create indexes for faster queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_directories_parent ON directories(parent_path)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_name ON files(name)")
    conn.commit()


def index_has_data(conn: sqlite3.Connection) -> bool:
    """Returns True if the index contains at least one directory record.

    Args:
        conn (sqlite3.Connection): SQLite database connection.

    Returns:
        bool: True if the directories table has any rows, False otherwise.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM directories LIMIT 1")
    return cursor.fetchone() is not None


def open_or_rescan(
    db_dir: Optional[str], directory: str, recursive: bool, level: Optional[int] = None
) -> sqlite3.Connection:
    """Opens the index, scanning the filesystem unless the user keeps a populated one.

    Args:
        db_dir (Optional[str]): Directory holding index databases. Defaults to
            the XDG index directory.
        directory (str): Directory to scan.
        recursive (bool): Whether to scan recursively.
        level (Optional[int]): Maximum depth level for recursion.

    Returns:
        sqlite3.Connection: A connection to a ready-to-query index.
    """
    db_path = index_db_path(db_dir, directory)
    index_existed = os.path.exists(db_path)
    conn = initialize_database(db_path)
    if (
        index_existed
        and index_has_data(conn)
        and console.confirm("Use the existing index?", default=True)
    ):
        return conn
    with console.progress() as p:
        task = p.add_task("Scanning", total=None)
        collect_directories(
            conn,
            directory,
            recursive,
            level,
            progress_cb=lambda d, f: p.update(
                task, description=f"Scanning  dirs {d:,}  files {f:,}"
            ),
        )
    return conn


def _escape_like(text: str) -> str:
    """Escapes SQL LIKE wildcards so paths match literally (ESCAPE '\\')."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def update_index_after_change(conn: sqlite3.Connection, action: str, path: Path) -> None:
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
                {
                    "action": "index_add_directory",
                    "status": "stat_failed",
                    "path": str(path),
                }
            )
            return
        cursor.execute(
            "INSERT OR IGNORE INTO directories (path, parent_path, mtime) VALUES (?, ?, ?)",
            (str(path), str(path.parent), stat_info.st_mtime),
        )
    conn.commit()


def close_database(conn: sqlite3.Connection) -> None:
    """Closes the database connection.

    Args:
        conn (sqlite3.Connection): SQLite database connection.
    """
    conn.close()
    logging.info({"action": "database_closed"})
