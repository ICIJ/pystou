#!/usr/bin/env python3
"""Cleanup subcommand for removing junk files from directories."""

import argparse
import logging
import os
import shlex
import shutil
import sys
from pathlib import Path
from typing import Optional

from common import trash
from common.cli import add_common_arguments
from common.fs_walker import is_excluded_dir
from common.interrupt import scanning
from common.logger import log_configuration, setup_logging
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


def add_cleanup_arguments(parser: argparse.ArgumentParser) -> None:
    """Adds cleanup-specific arguments to the parser.

    Args:
        parser: ArgumentParser to add arguments to.
    """
    add_common_arguments(parser)
    parser.add_argument(
        "--include",
        type=str,
        action="append",
        metavar="PATTERN",
        help="Additional file/directory names to remove (can be used multiple times)",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Only list junk files without removing them",
    )
    parser.add_argument(
        "--hard-delete",
        action="store_true",
        help="Permanently delete instead of moving to .pystou-trash",
    )
    parser.add_argument(
        "--trash-dir",
        default=None,
        metavar="PATH",
        help="Override the trash location (must be on the same filesystem)",
    )


def main(args: Optional[argparse.Namespace] = None) -> None:
    """Main entry point for cleanup.

    Args:
        args: Parsed arguments. If None, parses from command line.
    """
    if args is None:
        parser = argparse.ArgumentParser(description="Cleanup junk files script.")
        add_cleanup_arguments(parser)
        args = parser.parse_args()

    setup_logging("cleanup", args.log_dir)
    log_configuration(args)

    validate_directory_or_exit(args.directory)

    # Build the set of patterns to match
    junk_files = JUNK_FILES.copy()
    junk_dirs = JUNK_DIRS.copy()
    if args.include:
        for pattern in args.include:
            junk_files.add(pattern)

    # Find junk files
    with scanning("scan"):
        junk_items = find_junk(args.directory, args.recursive, junk_files, junk_dirs)

    if not junk_items:
        print("No junk files found.")
        logging.info({"action": "no_junk_found"})
        return

    print(f"Found {len(junk_items)} junk item(s):")
    for item in junk_items:
        print(f"  {item}")

    logging.info(
        {
            "action": "junk_found",
            "count": len(junk_items),
            "items": [str(i) for i in junk_items],
        }
    )

    if args.list_only:
        print("\n(Use without --list-only to remove)")
        return

    if args.dry_run:
        print("\nDry run: would remove the above items")
        logging.info({"action": "cleanup", "status": "dry_run"})
        return

    # Remove junk files
    with scanning("removal"):
        removed_count, skipped_count = remove_junk(
            junk_items,
            args.directory,
            hard_delete=args.hard_delete,
            trash_dir=args.trash_dir,
        )

    print(f"\nRemoved {removed_count}/{len(junk_items)} item(s)")
    if skipped_count > 0:
        print(f"Skipped {skipped_count} item(s) due to errors")
    logging.info(
        {
            "action": "cleanup_complete",
            "removed": removed_count,
            "skipped": skipped_count,
            "total": len(junk_items),
        }
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
    scanned = 0

    if recursive:
        # followlinks=False prevents infinite loops from symlink cycles
        for root, dirs, files in os.walk(directory_path, followlinks=False):
            root_path = Path(root)
            scanned += 1

            # Progress indicator every 1000 directories
            if scanned % 1000 == 0:
                print(f"Scanned {scanned} directories...", end="\r")

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
            print(f"Permission denied: {directory_path}")
            logging.warning({"action": "scan_error", "path": str(directory_path), "error": str(e)})

    if scanned >= 1000:
        print(f"Scanned {scanned} directories.    ")  # Clear progress line

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
            print(f"Error: {e}")
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
            print(f"Error removing {item}: {e}")
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


if __name__ == "__main__":
    main()
