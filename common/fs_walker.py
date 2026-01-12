import os
from pathlib import Path
import logging
import sqlite3
from typing import List, Optional, Tuple


class ScanContext:
    """Context object to track scanning state efficiently."""

    __slots__ = ("dir_count", "file_count", "update_interval", "_last_update")

    def __init__(self, update_interval: int = 100):
        self.dir_count = 0
        self.file_count = 0
        self.update_interval = update_interval
        self._last_update = 0

    def increment_dirs(self) -> None:
        self.dir_count += 1
        self._maybe_update_output()

    def increment_files(self) -> None:
        self.file_count += 1
        self._maybe_update_output()

    def _maybe_update_output(self) -> None:
        total = self.dir_count + self.file_count
        if total - self._last_update >= self.update_interval:
            self._last_update = total
            update_live_output(self.dir_count, self.file_count)

    def final_update(self) -> None:
        update_live_output(self.dir_count, self.file_count)
        print()  # Newline after scanning complete


def collect_directories(
    conn: sqlite3.Connection,
    directory: str,
    recursive: bool,
    level: Optional[int] = None,
) -> None:
    """Scans the filesystem and populates the database with directory and file information.

    Args:
        conn (sqlite3.Connection): SQLite database connection.
        directory (str): Directory to start scanning from.
        recursive (bool): Whether to scan directories recursively.
        level (Optional[int]): Maximum depth level for recursion (default: unlimited).
    """
    ctx = ScanContext(update_interval=100)
    clear_database(conn)
    scan_dir(Path(directory), 1, conn, recursive, level, ctx)
    ctx.final_update()


def clear_database(conn: sqlite3.Connection) -> None:
    """Clears existing data from the database.

    Args:
        conn (sqlite3.Connection): SQLite database connection.
    """
    cursor = conn.cursor()
    cursor.execute("DELETE FROM directories")
    cursor.execute("DELETE FROM files")
    conn.commit()


def scan_dir(
    current_dir: Path,
    current_level: int,
    conn: sqlite3.Connection,
    recursive: bool,
    level: Optional[int],
    ctx: ScanContext,
) -> None:
    """Recursively scans directories and updates the database.

    Args:
        current_dir (Path): Current directory being scanned.
        current_level (int): Current depth level.
        conn (sqlite3.Connection): SQLite database connection.
        recursive (bool): Whether to scan directories recursively.
        level (Optional[int]): Maximum depth level for recursion.
        ctx (ScanContext): Scanning context for counters and output.
    """
    try:
        with os.scandir(current_dir) as entries:
            dir_entries: List[Tuple[str, str, float]] = []
            file_entries: List[Tuple[str, str, int, float]] = []
            for entry in entries:
                full_path = Path(entry.path)
                if entry.is_dir(follow_symlinks=False):
                    stat_info = entry.stat(follow_symlinks=False)
                    dir_entries.append((str(full_path), str(current_dir), stat_info.st_mtime))
                    ctx.increment_dirs()
                    if recursive and (level is None or current_level < level):
                        scan_dir(
                            full_path,
                            current_level + 1,
                            conn,
                            recursive,
                            level,
                            ctx,
                        )
                elif entry.is_file(follow_symlinks=False):
                    stat_info = entry.stat(follow_symlinks=False)
                    file_entries.append((str(current_dir), entry.name, stat_info.st_size, stat_info.st_mtime))
                    ctx.increment_files()
            insert_entries(conn, dir_entries, file_entries)
    except PermissionError as e:
        print(f"\nPermission denied: {current_dir}")
        logging.error(
            {"action": "scan_error", "directory": str(current_dir), "error": str(e)}
        )


def update_live_output(dir_count: int, file_count: int) -> None:
    """Updates the live scanning output.

    Args:
        dir_count (int): Number of directories scanned.
        file_count (int): Number of files scanned.
    """
    formatted_dir_count = f"{dir_count:,}"
    formatted_file_count = f"{file_count:,}"
    print(
        f"Scanning directories: {formatted_dir_count}, files: {formatted_file_count}",
        end="\r",
        flush=True,
    )


def insert_entries(
    conn: sqlite3.Connection,
    dir_entries: List[Tuple[str, str, float]],
    file_entries: List[Tuple[str, str, int, float]],
) -> None:
    """Inserts directory and file entries into the database.

    Args:
        conn (sqlite3.Connection): SQLite database connection.
        dir_entries (List[Tuple[str, str, float]]): List of directory entries.
        file_entries (List[Tuple[str, str, int, float]]): List of file entries.
    """
    cursor = conn.cursor()
    if dir_entries:
        cursor.executemany(
            "INSERT OR IGNORE INTO directories (path, parent_path, mtime) VALUES (?, ?, ?)",
            dir_entries,
        )
    if file_entries:
        cursor.executemany(
            "INSERT OR IGNORE INTO files (directory_path, name, size, mtime) VALUES (?, ?, ?, ?)",
            file_entries,
        )
    conn.commit()
