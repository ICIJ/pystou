#!/usr/bin/env python3
"""Cleanup subcommand for removing junk files from directories."""

import logging
import os
import shlex
import shutil
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer

from common import console, trash
from common.cli import (
    DbDirOpt,
    DirectoryArg,
    DryRunOpt,
    HardDeleteOpt,
    LogDirOpt,
    RecursiveOpt,
    TrashDirOpt,
)
from common.fs_walker import is_excluded_dir
from common.logger import setup_logging
from common.validation import validate_directory_or_exit

# Default junk file patterns
JUNK_FILES: set[str] = {
    ".DS_Store",
    "._.DS_Store",
    "Thumbs.db",
    "desktop.ini",
    ".Spotlight-V100",
    ".Trashes",
    "ehthumbs.db",
    "ehthumbs_vista.db",
}

# Junk file prefixes (macOS resource forks)
JUNK_PREFIXES: set[str] = {
    "._",
}

# Junk directories
JUNK_DIRS: set[str] = {
    "__MACOSX",
    ".AppleDouble",
    ".LSOverride",
    ".TemporaryItems",
    ".fseventsd",
}


def cleanup_command(
    directory: DirectoryArg = ".",
    recursive: RecursiveOpt = False,
    include: Annotated[
        Optional[list[str]], typer.Option("--include", help="Extra file/dir names to remove.")
    ] = None,
    list_only: Annotated[
        bool, typer.Option("--list-only", help="List junk without removing.")
    ] = False,
    dry_run: DryRunOpt = False,
    hard_delete: HardDeleteOpt = False,
    trash_dir: TrashDirOpt = None,
    log_dir: LogDirOpt = ".",
    db_dir: DbDirOpt = ".",
) -> None:
    """Remove junk files (.DS_Store, Thumbs.db, etc.); quarantines by default."""
    setup_logging("cleanup", log_dir)
    logging.info(
        {
            "action": "configuration",
            "command": "cleanup",
            "directory": directory,
            "recursive": recursive,
            "list_only": list_only,
            "dry_run": dry_run,
            "hard_delete": hard_delete,
        }
    )
    validate_directory_or_exit(directory)

    junk_files = JUNK_FILES.copy()
    junk_dirs = JUNK_DIRS.copy()
    for pattern in include or []:
        junk_files.add(pattern)

    junk_items = find_junk(directory, recursive, junk_files, junk_dirs)
    if not junk_items:
        console.status("No junk files found.")
        return
    console.status(f"Found {len(junk_items)} junk item(s):")
    for item in junk_items:
        console.status(f"  {item}")
    logging.info(
        {
            "action": "junk_found",
            "count": len(junk_items),
            "items": [str(i) for i in junk_items],
        }
    )

    if list_only:
        console.status("(Use without --list-only to remove)")
        return
    if dry_run:
        console.status("Dry run: would remove the above items")
        logging.info({"action": "cleanup", "status": "dry_run"})
        return

    removed, skipped = remove_junk(
        junk_items, directory, hard_delete=hard_delete, trash_dir=trash_dir
    )
    verb = "Deleted" if hard_delete else "Quarantined"
    console.success(
        f"{verb} {removed}/{len(junk_items)} item(s)" + (f", skipped {skipped}" if skipped else "")
    )


def find_junk(
    directory: str,
    recursive: bool,
    junk_files: set[str],
    junk_dirs: set[str],
) -> list[Path]:
    """Finds junk files and directories.

    Args:
        directory: Directory to search.
        recursive: Whether to search recursively.
        junk_files: Set of junk file names.
        junk_dirs: Set of junk directory names.

    Returns:
        List of paths to junk items.
    """
    junk_items: list[Path] = []
    directory_path = Path(directory)

    if recursive:
        # followlinks=False prevents infinite loops from symlink cycles
        for root, dirs, files in os.walk(directory_path, followlinks=False):
            root_path = Path(root)

            # Check for junk directories
            for dir_name in dirs[:]:  # Copy to allow modification
                if is_excluded_dir(dir_name):
                    dirs.remove(dir_name)  # Don't descend into excluded dirs
                    continue
                dir_path = root_path / dir_name
                # Skip symlinks to avoid issues
                if dir_path.is_symlink():
                    continue
                if dir_name in junk_dirs:
                    junk_items.append(dir_path)
                    dirs.remove(dir_name)  # Don't descend into junk dirs

            # Check for junk files
            for file_name in files:
                file_path = root_path / file_name
                # Skip symlinks
                if file_path.is_symlink():
                    continue
                if is_junk_file(file_name, junk_files):
                    junk_items.append(file_path)
    else:
        try:
            for entry in os.scandir(directory_path):
                # Skip the trash directory and other excluded dirs
                if entry.is_dir(follow_symlinks=False) and is_excluded_dir(entry.name):
                    continue
                # Skip symlinks
                if entry.is_symlink():
                    continue
                if (entry.is_dir(follow_symlinks=False) and entry.name in junk_dirs) or (
                    entry.is_file(follow_symlinks=False) and is_junk_file(entry.name, junk_files)
                ):
                    junk_items.append(Path(entry.path))
        except PermissionError as e:
            console.error(f"Permission denied: {directory_path}")
            logging.warning({"action": "scan_error", "path": str(directory_path), "error": str(e)})

    return junk_items


def is_junk_file(filename: str, junk_files: set[str]) -> bool:
    """Checks if a filename is a junk file.

    Args:
        filename: Name of the file.
        junk_files: Set of junk file names.

    Returns:
        True if the file is junk, False otherwise.
    """
    if filename in junk_files:
        return True

    # Check prefixes (e.g., ._ files)
    return any(filename.startswith(prefix) for prefix in JUNK_PREFIXES)


def remove_junk(
    junk_items: list[Path],
    op_root: str = ".",
    *,
    hard_delete: bool = False,
    trash_dir: Optional[str] = None,
) -> tuple:
    """Removes junk items, quarantining by default (hard-delete on request).

    Args:
        junk_items: Paths to remove.
        op_root: Directory hosting the trash (the cleanup target dir).
        hard_delete: If True, permanently delete instead of quarantining.
        trash_dir: Optional trash location override.

    Returns:
        Tuple of (removed_count, skipped_count).
    """
    existing = [item for item in junk_items if item.exists() or item.is_symlink()]
    skipped = len(junk_items) - len(existing)

    if not hard_delete:
        try:
            trash.quarantine(
                existing,
                op_root,
                operation="cleanup",
                command=shlex.join(sys.argv),
                trash_dir=trash_dir,
            )
        except (trash.CrossDeviceTrashError, trash.TrashUnavailableError) as e:
            console.error(str(e))
            logging.error({"action": "cleanup", "status": "trash_error", "error": str(e)})
            return 0, len(junk_items)
        return len(existing), skipped

    removed = 0
    for item in existing:
        try:
            if item.is_symlink():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            removed += 1
            logging.info({"action": "remove_junk", "status": "success", "path": str(item)})
        except OSError as e:
            console.error(f"Error removing {item}: {e}")
            logging.error(
                {
                    "action": "remove_junk",
                    "status": "error",
                    "path": str(item),
                    "error": str(e),
                }
            )
            skipped += 1
    return removed, skipped
