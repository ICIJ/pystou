#!/usr/bin/env python3
"""Empty subcommand for finding and removing empty directories."""

import errno
import logging
import os
from pathlib import Path
from typing import Annotated, Optional

import typer

from common import console
from common.cli import (
    DirectoryArg,
    DryRunOpt,
    LogDirOpt,
    RecursiveOpt,
    ThreadsOpt,
)
from common.fs_walker import is_excluded_dir, walk
from common.logger import setup_logging
from common.validation import validate_directory_or_exit


def empty_command(
    directory: DirectoryArg = ".",
    recursive: RecursiveOpt = False,
    threads: ThreadsOpt = None,
    list_only: Annotated[
        bool, typer.Option("--list-only", help="List empty dirs without removing.")
    ] = False,
    include_hidden: Annotated[
        bool, typer.Option("--include-hidden", help="Include hidden directories.")
    ] = False,
    dry_run: DryRunOpt = False,
    log_dir: LogDirOpt = None,
) -> None:
    """Find and remove empty directories; no quarantine (empty dirs hold no data)."""
    setup_logging("empty", log_dir)
    logging.info(
        {
            "action": "configuration",
            "command": "empty",
            "directory": directory,
            "recursive": recursive,
            "threads": threads,
            "list_only": list_only,
            "include_hidden": include_hidden,
            "dry_run": dry_run,
        }
    )
    validate_directory_or_exit(directory)

    empty_dirs = find_empty_directories(directory, recursive, include_hidden, threads)

    if not empty_dirs:
        console.status("No empty directories found.")
        logging.info({"action": "no_empty_dirs_found"})
        return

    console.status(f"Found {len(empty_dirs)} empty directory(ies):")
    for d in empty_dirs:
        console.status(f"  {d}")
    logging.info(
        {
            "action": "empty_dirs_found",
            "count": len(empty_dirs),
            "directories": [str(d) for d in empty_dirs],
        }
    )

    if list_only:
        console.status("(use without --list-only to remove)")
        return

    if dry_run:
        console.status("Dry run: would remove the above directories")
        logging.info({"action": "remove_empty", "status": "dry_run"})
        return

    removed_count, skipped_count = remove_empty_directories(empty_dirs)
    console.success(
        f"Removed {removed_count}/{len(empty_dirs)} directory(ies)"
        + (f", skipped {skipped_count}" if skipped_count else "")
    )
    logging.info(
        {
            "action": "remove_empty_complete",
            "removed": removed_count,
            "skipped": skipped_count,
            "total": len(empty_dirs),
        }
    )


def find_empty_directories(
    directory: str,
    recursive: bool,
    include_hidden: bool,
    threads: Optional[int] = None,
) -> list[Path]:
    """Finds empty directories.

    Args:
        directory: Directory to search.
        recursive: Whether to search recursively.
        include_hidden: Whether to include hidden directories.
        threads: Scan workers; None picks the default.

    Returns:
        List of paths to empty directories, sorted deepest first.
    """
    empty_dirs: list[Path] = []
    directory_path = Path(directory)

    if recursive:
        for scan in walk(directory_path, threads=threads):
            if scan.error is not None:
                logging.warning(
                    {"action": "scan_error", "path": str(scan.path), "error": str(scan.error)}
                )
                continue
            if scan.path == directory_path or scan.entries:
                continue
            if not include_hidden and scan.path.name.startswith("."):
                continue
            empty_dirs.append(scan.path)
    else:
        try:
            for entry in os.scandir(directory_path):
                # Skip symlinks
                if entry.is_symlink():
                    continue

                if entry.is_dir(follow_symlinks=False):
                    dir_path = Path(entry.path)

                    # Skip the trash directory
                    if is_excluded_dir(entry.name):
                        continue

                    # Skip hidden directories if not included
                    if not include_hidden and dir_path.name.startswith("."):
                        continue

                    if is_directory_empty(dir_path):
                        empty_dirs.append(dir_path)
        except PermissionError as e:
            console.error(f"Permission denied: {directory_path}")
            logging.warning({"action": "scan_error", "path": str(directory_path), "error": str(e)})

    # Deepest first for safe removal; the path breaks ties so runs are repeatable.
    empty_dirs.sort(key=lambda p: (-len(p.parts), str(p)))

    return empty_dirs


def is_directory_empty(dir_path: Path) -> bool:
    """Checks if a directory is empty.

    Args:
        dir_path: Path to the directory.

    Returns:
        True if the directory is empty, False otherwise.
    """
    try:
        with os.scandir(dir_path) as entries:
            return next(entries, None) is None
    except PermissionError:
        return False
    except FileNotFoundError:
        # Directory was deleted between listing and checking
        return False
    except OSError:
        return False


def remove_empty_directories(empty_dirs: list[Path]) -> tuple:
    """Removes empty directories.

    Args:
        empty_dirs: List of paths to remove (should be sorted deepest first).

    Returns:
        Tuple of (removed_count, skipped_count).
    """
    removed = 0
    skipped = 0

    for dir_path in empty_dirs:
        try:
            # Check if it still exists and is still empty
            if not dir_path.exists():
                logging.warning(
                    {
                        "action": "remove_empty_dir",
                        "status": "already_deleted",
                        "path": str(dir_path),
                    }
                )
                skipped += 1
                continue

            if dir_path.is_symlink():
                # Skip symlinks for safety
                logging.warning(
                    {
                        "action": "remove_empty_dir",
                        "status": "symlink_skipped",
                        "path": str(dir_path),
                    }
                )
                skipped += 1
                continue

            dir_path.rmdir()
            removed += 1
            logging.info(
                {
                    "action": "remove_empty_dir",
                    "status": "success",
                    "path": str(dir_path),
                }
            )

        except FileNotFoundError:
            # Directory was deleted between check and removal
            logging.warning(
                {
                    "action": "remove_empty_dir",
                    "status": "not_found",
                    "path": str(dir_path),
                }
            )
            skipped += 1

        except PermissionError as e:
            console.error(f"Permission denied: {dir_path}")
            logging.error(
                {
                    "action": "remove_empty_dir",
                    "status": "permission_denied",
                    "path": str(dir_path),
                    "error": str(e),
                }
            )
            skipped += 1

        except OSError as e:
            # Directory might not be empty anymore or have other issues
            if e.errno == errno.ENOTEMPTY:
                logging.warning(
                    {
                        "action": "remove_empty_dir",
                        "status": "not_empty",
                        "path": str(dir_path),
                    }
                )
            else:
                console.error(f"Error removing {dir_path}: {e}")
                logging.error(
                    {
                        "action": "remove_empty_dir",
                        "status": "error",
                        "path": str(dir_path),
                        "error": str(e),
                    }
                )
            skipped += 1

    return removed, skipped
