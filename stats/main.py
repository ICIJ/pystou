#!/usr/bin/env python3
"""Stats subcommand for displaying directory statistics."""

import heapq
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Annotated, Any, Optional

import typer

from common import console
from common.cli import (
    DirectoryArg,
    LogDirOpt,
    RecursiveOpt,
    ThreadsOpt,
)
from common.fs_walker import is_excluded_dir, walk
from common.logger import setup_logging
from common.utils import ARCHIVE_EXTENSIONS
from common.validation import validate_directory_or_exit


def stats_command(
    directory: DirectoryArg = ".",
    recursive: RecursiveOpt = False,
    threads: ThreadsOpt = None,
    top: Annotated[int, typer.Option("--top", min=0, help="Number of top items to show.")] = 10,
    by_extension: Annotated[
        bool, typer.Option("--by-extension", help="Show breakdown by extension.")
    ] = False,
    by_size: Annotated[bool, typer.Option("--by-size", help="Show largest files.")] = False,
    json_out: Annotated[bool, typer.Option("--json", help="Output stats as JSON.")] = False,
    log_dir: LogDirOpt = None,
) -> None:
    """Display directory statistics: file counts, sizes, extensions, largest files."""
    setup_logging("stats", log_dir)
    logging.info(
        {
            "action": "configuration",
            "command": "stats",
            "directory": directory,
            "recursive": recursive,
            "threads": threads,
            "top": top,
            "by_extension": by_extension,
            "by_size": by_size,
            "json": json_out,
        }
    )
    validate_directory_or_exit(directory)

    stats = collect_stats(directory, recursive, top_n=top, threads=threads)

    if json_out:
        output = {
            "summary": stats["summary"],
            "by_extension": dict(stats["by_extension"]),
            "largest_files": [
                {"path": path, "size": size} for path, size in stats["largest_files"][:top]
            ],
            "empty_directories": stats["empty_directories"][:top],
        }
        console.print_json(output)
        return

    # Summary table
    summary = stats["summary"]
    t = console.table("Directory Statistics", ["Metric", "Value"])
    t.add_row("Total files", f"{summary['total_files']:,}")
    t.add_row("Total directories", f"{summary['total_dirs']:,}")
    t.add_row("Total size", console.human_size(summary["total_size"]))
    t.add_row("Archive files", f"{summary['archive_files']:,}")
    t.add_row("Empty directories", f"{summary['empty_dirs']:,}")
    if summary["symlinks_skipped"] > 0:
        t.add_row("Symlinks skipped", f"{summary['symlinks_skipped']:,}")
    console.print_table(t)

    # Extension breakdown
    if by_extension:
        sorted_by_count = sorted(
            stats["by_extension"].items(),
            key=lambda x: x[1]["count"],
            reverse=True,
        )[:top]
        te = console.table(f"Top {top} Extensions by Count", ["Extension", "Files", "Size"])
        for ext, data in sorted_by_count:
            te.add_row(ext, f"{data['count']:,}", console.human_size(data["size"]))
        console.print_table(te)

    # Largest files
    if by_size:
        ts = console.table(f"Top {top} Largest Files", ["Size", "Path"])
        for path, size in stats["largest_files"][:top]:
            ts.add_row(console.human_size(size), path)
        console.print_table(ts)


def collect_stats(
    directory: str, recursive: bool, top_n: int = 10, threads: Optional[int] = None
) -> dict:
    """Collects statistics from the directory.

    Args:
        directory: Directory to analyze.
        recursive: Whether to analyze recursively.
        top_n: Number of top files to track (for memory efficiency).
        threads: Scan workers; None picks the default.

    Returns:
        Dictionary with collected statistics.
    """
    stats: dict[str, Any] = {
        "summary": {
            "total_files": 0,
            "total_dirs": 0,
            "total_size": 0,
            "empty_dirs": 0,
            "archive_files": 0,
            "symlinks_skipped": 0,
            "errors": 0,
        },
        "by_extension": defaultdict(lambda: {"count": 0, "size": 0}),
        "largest_files": [],  # Will be a heap of (size, path) tuples
        "empty_directories": [],
    }

    archive_extensions = set(ARCHIVE_EXTENSIONS)

    directory_path = Path(directory)

    if recursive:
        for scan in walk(directory_path, threads=threads):
            if scan.error is not None:
                stats["summary"]["errors"] += 1
                continue
            if scan.path != directory_path and not scan.entries:
                stats["summary"]["empty_dirs"] += 1
                if len(stats["empty_directories"]) < top_n:
                    stats["empty_directories"].append(str(scan.path))
            for entry in scan.entries:
                # is_dir() follows symlinks, reproducing how os.walk split dirs
                # from files, so total_dirs keeps counting symlinked directories.
                if entry.is_dir():
                    if is_excluded_dir(entry.name):
                        continue
                    stats["summary"]["total_dirs"] += 1
                    if entry.is_symlink():
                        stats["summary"]["symlinks_skipped"] += 1
                elif entry.is_symlink():
                    stats["summary"]["symlinks_skipped"] += 1
                else:
                    process_file(entry, stats, archive_extensions, top_n)
    else:
        try:
            for entry in os.scandir(directory_path):
                # Skip symlinks
                if entry.is_symlink():
                    stats["summary"]["symlinks_skipped"] += 1
                    continue

                if entry.is_dir(follow_symlinks=False):
                    # Skip the trash directory
                    if is_excluded_dir(entry.name):
                        continue
                    stats["summary"]["total_dirs"] += 1
                    try:
                        if not any(Path(entry.path).iterdir()):
                            stats["summary"]["empty_dirs"] += 1
                            if len(stats["empty_directories"]) < top_n:
                                stats["empty_directories"].append(entry.path)
                    except PermissionError:
                        stats["summary"]["errors"] += 1
                    except FileNotFoundError:
                        pass
                elif entry.is_file(follow_symlinks=False):
                    process_file(entry, stats, archive_extensions, top_n)
        except PermissionError as e:
            console.error(f"Permission denied: {directory_path}")
            logging.warning({"action": "scan_error", "path": str(directory_path), "error": str(e)})
            stats["summary"]["errors"] += 1

    # Convert heap to sorted list (largest first)
    stats["largest_files"] = [
        (path, size) for size, path in sorted(stats["largest_files"], reverse=True)
    ]
    # --json prints these verbatim, and the scan reaches directories in whatever
    # order the workers finish, so both are ordered here to keep runs comparable.
    stats["by_extension"] = dict(sorted(stats["by_extension"].items()))
    stats["empty_directories"].sort()

    return stats


def process_file(entry: os.DirEntry, stats: dict, archive_extensions: set, top_n: int) -> None:
    """Processes a single file and updates statistics.

    Args:
        entry: Directory entry for the file, from a scan that already skipped
            symlinks.
        stats: Statistics dictionary to update.
        archive_extensions: Set of archive file extensions.
        top_n: Number of largest files to track.
    """
    try:
        size = entry.stat(follow_symlinks=False).st_size
    except FileNotFoundError:
        # File deleted between listing and stat
        return
    except PermissionError:
        stats["summary"]["errors"] += 1
        return
    except OSError:
        stats["summary"]["errors"] += 1
        return

    stats["summary"]["total_files"] += 1
    stats["summary"]["total_size"] += size

    ext = Path(entry.name).suffix.lower() or "(no extension)"
    stats["by_extension"][ext]["count"] += 1
    stats["by_extension"][ext]["size"] += size

    if ext in archive_extensions:
        stats["summary"]["archive_files"] += 1

    # Use a min-heap to efficiently track top N largest files
    # We store (size, path) and keep only the largest N
    if len(stats["largest_files"]) < top_n:
        heapq.heappush(stats["largest_files"], (size, entry.path))
    elif stats["largest_files"] and size > stats["largest_files"][0][0]:
        heapq.heapreplace(stats["largest_files"], (size, entry.path))
