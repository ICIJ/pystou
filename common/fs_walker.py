import logging
import os
import sqlite3
from pathlib import Path
from typing import Optional

EXCLUDED_DIR_NAMES = {".pystou-trash"}


def is_excluded_dir(name: str) -> bool:
    """Returns True for directory names that no command should descend into."""
    return name in EXCLUDED_DIR_NAMES


class ScanContext:
    """Context object to track scanning state efficiently."""

    __slots__ = ("_last_update", "dir_count", "file_count", "update_interval")

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
    """Scans the filesystem and populates the database.

    Args:
        conn (sqlite3.Connection): SQLite database connection.
        directory (str): Directory to start scanning from.
        recursive (bool): Whether to scan directories recursively.
        level (Optional[int]): Maximum depth level for recursion (default: unlimited).
    """
    ctx = ScanContext(update_interval=100)
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
            print(f"\nPermission denied: {current_dir}")
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
