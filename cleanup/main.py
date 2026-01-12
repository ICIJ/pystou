#!/usr/bin/env python3
"""Cleanup subcommand for removing junk files from directories."""

import argparse
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Set

from common.logger import setup_logging
from common.cli import add_common_arguments

# Default junk file patterns
JUNK_FILES: Set[str] = {
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
JUNK_PREFIXES: Set[str] = {
    "._",
}

# Junk directories
JUNK_DIRS: Set[str] = {
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

    # Validate directory
    directory_path = Path(args.directory)
    if not directory_path.exists():
        print(f"Error: Directory does not exist: {args.directory}")
        logging.error({"action": "error", "message": "Directory not found", "path": args.directory})
        sys.exit(1)
    if not directory_path.is_dir():
        print(f"Error: Not a directory: {args.directory}")
        logging.error({"action": "error", "message": "Not a directory", "path": args.directory})
        sys.exit(1)

    # Build the set of patterns to match
    junk_files = JUNK_FILES.copy()
    junk_dirs = JUNK_DIRS.copy()
    if args.include:
        for pattern in args.include:
            junk_files.add(pattern)

    # Find junk files
    try:
        junk_items = find_junk(
            args.directory, args.recursive, junk_files, junk_dirs
        )
    except KeyboardInterrupt:
        print("\nScan interrupted by user.")
        logging.info({"action": "scan_interrupted"})
        sys.exit(130)

    if not junk_items:
        print("No junk files found.")
        logging.info({"action": "no_junk_found"})
        return

    print(f"Found {len(junk_items)} junk item(s):")
    for item in junk_items:
        print(f"  {item}")

    logging.info({
        "action": "junk_found",
        "count": len(junk_items),
        "items": [str(i) for i in junk_items],
    })

    if args.list_only:
        print("\n(Use without --list-only to remove)")
        return

    if args.dry_run:
        print("\nDry run: would remove the above items")
        logging.info({"action": "cleanup", "status": "dry_run"})
        return

    # Remove junk files
    try:
        removed_count, skipped_count = remove_junk(junk_items)
    except KeyboardInterrupt:
        print("\nRemoval interrupted by user.")
        logging.info({"action": "removal_interrupted"})
        sys.exit(130)

    print(f"\nRemoved {removed_count}/{len(junk_items)} item(s)")
    if skipped_count > 0:
        print(f"Skipped {skipped_count} item(s) due to errors")
    logging.info({
        "action": "cleanup_complete",
        "removed": removed_count,
        "skipped": skipped_count,
        "total": len(junk_items),
    })


def log_configuration(args) -> None:
    """Logs the configuration used to run the script."""
    config = {
        k: v for k, v in vars(args).items()
        if not k.startswith("_") and k not in ("func", "command")
    }
    config["action"] = "configuration"
    logging.info(config)


def find_junk(
    directory: str,
    recursive: bool,
    junk_files: Set[str],
    junk_dirs: Set[str],
) -> List[Path]:
    """Finds junk files and directories.

    Args:
        directory: Directory to search.
        recursive: Whether to search recursively.
        junk_files: Set of junk file names.
        junk_dirs: Set of junk directory names.

    Returns:
        List of paths to junk items.
    """
    junk_items: List[Path] = []
    directory_path = Path(directory)
    scanned = 0

    if recursive:
        # followlinks=False prevents infinite loops from symlink cycles
        for root, dirs, files in os.walk(directory_path, followlinks=False):
            root_path = Path(root)
            scanned += 1

            # Progress indicator every 1000 directories
            if scanned % 1000 == 0:
                print(f"  Scanned {scanned} directories...", end="\r")

            # Check for junk directories
            for dir_name in dirs[:]:  # Copy to allow modification
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
                # Skip symlinks
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False) and entry.name in junk_dirs:
                    junk_items.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False) and is_junk_file(entry.name, junk_files):
                    junk_items.append(Path(entry.path))
        except PermissionError as e:
            print(f"Permission denied: {directory_path}")
            logging.warning({"action": "scan_error", "path": str(directory_path), "error": str(e)})

    if scanned >= 1000:
        print(f"  Scanned {scanned} directories.    ")  # Clear progress line

    return junk_items


def is_junk_file(filename: str, junk_files: Set[str]) -> bool:
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
    for prefix in JUNK_PREFIXES:
        if filename.startswith(prefix):
            return True

    return False


def remove_junk(junk_items: List[Path]) -> tuple:
    """Removes junk files and directories.

    Args:
        junk_items: List of paths to remove.

    Returns:
        Tuple of (removed_count, skipped_count).
    """
    removed = 0
    skipped = 0
    total = len(junk_items)

    for i, item in enumerate(junk_items, 1):
        # Progress indicator
        if total > 10 and i % 10 == 0:
            print(f"  Removing {i}/{total}...", end="\r")

        try:
            if not item.exists():
                # File was already deleted (race condition)
                logging.warning({
                    "action": "remove_junk",
                    "status": "already_deleted",
                    "path": str(item),
                })
                skipped += 1
                continue

            if item.is_symlink():
                # Don't follow symlinks, just remove the link
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

            removed += 1
            logging.info({
                "action": "remove_junk",
                "status": "success",
                "path": str(item),
            })

        except FileNotFoundError:
            # Race condition: file deleted between check and removal
            logging.warning({
                "action": "remove_junk",
                "status": "not_found",
                "path": str(item),
            })
            skipped += 1

        except PermissionError as e:
            print(f"Permission denied: {item}")
            logging.error({
                "action": "remove_junk",
                "status": "permission_denied",
                "path": str(item),
                "error": str(e),
            })
            skipped += 1

        except OSError as e:
            print(f"Error removing {item}: {e}")
            logging.error({
                "action": "remove_junk",
                "status": "error",
                "path": str(item),
                "error": str(e),
            })
            skipped += 1

    if total > 10:
        print(f"  Removed {removed}/{total} items.    ")  # Clear progress line

    return removed, skipped


if __name__ == "__main__":
    main()
