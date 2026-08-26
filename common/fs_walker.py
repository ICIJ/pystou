import contextlib
import logging
import os
import queue
import sqlite3
import sys
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, NamedTuple, Optional

from common.errors import UndecodablePathError

EXCLUDED_DIR_NAMES = {".pystou-trash"}


def is_excluded_dir(name: str) -> bool:
    """Returns True for directory names that no command should descend into."""
    return name in EXCLUDED_DIR_NAMES


class DirScan(NamedTuple):
    """One directory's listing.

    Attributes:
        path (Path): The directory that was listed.
        entries (list): Its ``os.DirEntry`` objects; empty when ``error`` is set.
        error (Optional[OSError]): Why the listing failed, or None.
    """

    path: Path
    entries: list
    error: Optional[OSError]


def default_threads() -> int:
    """Scan workers when the user did not pick a number.

    Sized for latency, not for CPU: the work is blocking ``scandir`` calls, so
    more workers than cores pays off on a network mount. Capped so a throttling
    fileserver is never hit with unbounded concurrency.
    """
    return min(32, (os.cpu_count() or 1) * 4)


def walk(
    root,
    *,
    recursive: bool = True,
    max_depth: Optional[int] = None,
    threads: Optional[int] = None,
    prune: Optional[Callable[[os.DirEntry], bool]] = None,
) -> Iterator[DirScan]:
    """Lists a tree with one ``scandir`` per worker thread.

    Yields one :class:`DirScan` per directory, the root first and the rest in
    completion order. Results are yielded on the *calling* thread, so consumers
    stay single-threaded and need no locks of their own.

    Args:
        root: Directory to start from.
        recursive (bool): Whether to descend past the root.
        max_depth (Optional[int]): Levels below the root to visit. None is
            unlimited, 0 visits only the root, 1 the root and its children.
        threads (Optional[int]): Worker count; defaults to
            :func:`default_threads`.
        prune: Called with a directory entry; return True to skip its subtree.
            ``.pystou-trash`` is always skipped regardless.

    Yields:
        DirScan: One per directory visited.
    """
    root = Path(root)
    workers = threads if threads and threads > 0 else default_threads()
    results: queue.Queue = queue.Queue(maxsize=workers * 4)
    stop = threading.Event()
    lock = threading.Lock()
    pending = 1
    done = object()

    def emit(item) -> bool:
        # Polls instead of blocking forever: a consumer that walks away must not
        # strand a worker inside put(), because the pool's threads are joined at
        # interpreter exit and would hang the process.
        while not stop.is_set():
            try:
                results.put(item, timeout=0.1)
                return True
            except queue.Full:
                continue
        return False

    def descend(entry: os.DirEntry, depth: int) -> bool:
        if not recursive or is_excluded_dir(entry.name):
            return False
        if not entry.is_dir(follow_symlinks=False):
            return False
        if max_depth is not None and depth >= max_depth:
            return False
        return prune is None or not prune(entry)

    def scan(path: Path, depth: int) -> None:
        nonlocal pending
        children: list = []
        try:
            try:
                with os.scandir(path) as it:
                    entries = list(it)
            except OSError as e:
                emit(DirScan(path, [], e))
            else:
                children = [path / e.name for e in entries if descend(e, depth)]
                # Count children before releasing this task, so the counter can
                # only reach zero when the whole tree is really finished.
                with lock:
                    pending += len(children)
                if not emit(DirScan(path, entries, None)):
                    with lock:
                        pending -= len(children)
                    children = []
        finally:
            with lock:
                pending -= 1
                finished = pending == 0
            if finished:
                emit(done)
        for child in children:
            if stop.is_set():
                return
            with contextlib.suppress(RuntimeError):  # pool closed mid-walk
                executor.submit(scan, child, depth + 1)

    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pystou-scan")
    try:
        executor.submit(scan, root, 0)
        while True:
            item = results.get()
            if item is done:
                return
            yield item
    finally:
        stop.set()
        executor.shutdown(wait=False, cancel_futures=True)


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
    threads: Optional[int] = None,
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
        threads (Optional[int]): Scan workers; None picks the default.
    """
    ctx = ScanContext(update_interval=100, progress_cb=progress_cb)
    clear_database(conn)
    scan_tree(Path(directory), conn, recursive, level, ctx, threads)
    ctx.final_update()


def scan_tree(
    root_dir: Path,
    conn: sqlite3.Connection,
    recursive: bool,
    level: Optional[int],
    ctx: ScanContext,
    threads: Optional[int] = None,
) -> None:
    """Scans a tree in parallel and inserts what it finds.

    Args:
        root_dir (Path): Directory to start from.
        conn (sqlite3.Connection): SQLite database connection.
        recursive (bool): Whether to scan recursively.
        level (Optional[int]): Maximum depth level, 1 being the root alone.
        ctx (ScanContext): Scanning context for counters and output.
        threads (Optional[int]): Scan workers; None picks the default.
    """
    # level is 1-based and counts the root; walk's max_depth counts levels below it.
    max_depth = None if level is None else level - 1
    for scan in walk(root_dir, recursive=recursive, max_depth=max_depth, threads=threads):
        if scan.error is not None:
            if isinstance(scan.error, PermissionError):
                print(f"\nPermission denied: {scan.path}", file=sys.stderr)
                logging.error(
                    {
                        "action": "scan_error",
                        "directory": str(scan.path),
                        "error": str(scan.error),
                    }
                )
            else:
                logging.warning(
                    {
                        "action": "scan_error",
                        "directory": str(scan.path),
                        "error": str(scan.error),
                    }
                )
            continue
        dir_entries: list[tuple[str, str, float]] = []
        file_entries: list[tuple[str, str, int, float]] = []
        for entry in scan.entries:
            full_path = scan.path / entry.name
            try:
                if entry.is_dir(follow_symlinks=False):
                    if is_excluded_dir(entry.name):
                        continue
                    stat_info = entry.stat(follow_symlinks=False)
                    dir_entries.append((str(full_path), str(scan.path), stat_info.st_mtime))
                    ctx.increment_dirs()
                elif entry.is_file(follow_symlinks=False):
                    stat_info = entry.stat(follow_symlinks=False)
                    file_entries.append(
                        (str(scan.path), entry.name, stat_info.st_size, stat_info.st_mtime)
                    )
                    ctx.increment_files()
            except OSError as e:
                # One bad entry must not abort its siblings.
                logging.warning(
                    {"action": "scan_entry_error", "path": str(full_path), "error": str(e)}
                )
        insert_entries(conn, dir_entries, file_entries)


def _reject_undecodable(
    dir_entries: list[tuple[str, str, float]],
    file_entries: list[tuple[str, str, int, float]],
) -> None:
    """Raises :class:`UndecodablePathError` for the first name SQLite cannot store."""
    for path, _parent, _mtime in dir_entries:
        _reject_undecodable_name(path)
    for directory, name, _size, _mtime in file_entries:
        _reject_undecodable_name(directory)
        _reject_undecodable_name(name)


def _reject_undecodable_name(name: str) -> None:
    try:
        name.encode("utf-8")
    except UnicodeEncodeError as e:
        raise UndecodablePathError(name) from e


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
    # SQLite TEXT is UTF-8, so a name the filesystem accepted but Python
    # surfaces as surrogates cannot be stored. Fail here, where the offending
    # name is still known, rather than letting sqlite3 raise anonymously.
    _reject_undecodable(dir_entries, file_entries)
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
