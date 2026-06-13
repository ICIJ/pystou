import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Callable, Optional

EXCLUDED_DIR_NAMES = {".pystou-trash"}


def is_excluded_dir(name: str) -> bool:
    """Returns True for directory names that no command should descend into."""
    return name in EXCLUDED_DIR_NAMES


class ScanContext:
    """Context object to track scanning state efficiently."""

    __slots__ = ("_last_update", "_progress_cb", "dir_count", "file_count", "update_interval")

    def __init__(
        self,
        update_interval: int = 100,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ):
        self.dir_count = 0
        self.file_count = 0
        self.update_interval = update_interval
        self._last_update = 0
        self._progress_cb = progress_cb

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
            if self._progress_cb is not None:
                self._progress_cb(self.dir_count, self.file_count)

    def final_update(self) -> None:
        if self._progress_cb is not None:
            self._progress_cb(self.dir_count, self.file_count)


def collect_directories(
    conn: sqlite3.Connection,
    directory: str,
    recursive: bool,
    level: Optional[int] = None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> None:
    """Scans the filesystem and populates the database.

    Args:
        conn (sqlite3.Connection): SQLite database connection.
        directory (str): Directory to start scanning from.
        recursive (bool): Whether to scan directories recursively.
        level (Optional[int]): Maximum depth level for recursion (default: unlimited).
        progress_cb: Optional callback invoked as ``progress_cb(dir_count, file_count)``
            at regular intervals during the scan and once on completion.  When
            *None* (the default) no progress output is produced.
    """
    ctx = ScanContext(update_interval=100, progress_cb=progress_cb)
    clear_database(conn)
    scan_tree(Path(directory), conn, recursive, level, ctx)
    ctx.final_update()


def scan_tree(
    root_dir: Path,
    conn: sqlite3.Connection,
    recursive: bool,
    level: Optional[int],
    ctx: ScanContext,
) -> None:
    """Scans a tree iteratively (explicit stack avoids RecursionError on deep trees).

    Args:
        root_dir (Path): Directory to start from.
        conn (sqlite3.Connection): SQLite database connection.
        recursive (bool): Whether to scan recursively.
        level (Optional[int]): Maximum depth level for recursion.
        ctx (ScanContext): Scanning context for counters and output.
    """
    stack: list[tuple[Path, int]] = [(root_dir, 1)]
    while stack:
        current_dir, current_level = stack.pop()
        try:
            with os.scandir(current_dir) as entries:
                dir_entries: list[tuple[str, str, float]] = []
                file_entries: list[tuple[str, str, int, float]] = []
                subdirs: list[Path] = []
                for entry in entries:
                    full_path = Path(entry.path)
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if is_excluded_dir(entry.name):
                                continue
                            stat_info = entry.stat(follow_symlinks=False)
                            dir_entries.append(
                                (str(full_path), str(current_dir), stat_info.st_mtime)
                            )
                            ctx.increment_dirs()
                            if recursive and (level is None or current_level < level):
                                subdirs.append(full_path)
                        elif entry.is_file(follow_symlinks=False):
                            stat_info = entry.stat(follow_symlinks=False)
                            file_entries.append(
                                (
                                    str(current_dir),
                                    entry.name,
                                    stat_info.st_size,
                                    stat_info.st_mtime,
                                )
                            )
                            ctx.increment_files()
                    except OSError as e:
                        # One bad entry must not abort its siblings.
                        logging.warning(
                            {
                                "action": "scan_entry_error",
                                "path": str(full_path),
                                "error": str(e),
                            }
                        )
                insert_entries(conn, dir_entries, file_entries)
                # reversed() so siblings are popped in scandir order (matches the
                # original recursive traversal).
                for subdir in reversed(subdirs):
                    stack.append((subdir, current_level + 1))
        except PermissionError as e:
            print(f"\nPermission denied: {current_dir}", file=sys.stderr)
            logging.error({"action": "scan_error", "directory": str(current_dir), "error": str(e)})
        except OSError as e:
            logging.warning(
                {"action": "scan_error", "directory": str(current_dir), "error": str(e)}
            )


def clear_database(conn: sqlite3.Connection) -> None:
    """Clears existing data from the database.

    Args:
        conn (sqlite3.Connection): SQLite database connection.
    """
    cursor = conn.cursor()
    cursor.execute("DELETE FROM directories")
    cursor.execute("DELETE FROM files")
    conn.commit()


def insert_entries(
    conn: sqlite3.Connection,
    dir_entries: list[tuple[str, str, float]],
    file_entries: list[tuple[str, str, int, float]],
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
