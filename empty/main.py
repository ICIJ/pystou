#!/usr/bin/env python3
"""Empty subcommand for finding and removing empty directories."""

import argparse
import logging
import os
from pathlib import Path
from typing import List, Optional

from common.logger import setup_logging
from common.cli import add_common_arguments


def add_empty_arguments(parser: argparse.ArgumentParser) -> None:
    """Adds empty-specific arguments to the parser.

    Args:
        parser: ArgumentParser to add arguments to.
    """
    add_common_arguments(parser)
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Only list empty directories without removing them",
    )
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Include hidden directories (starting with .)",
    )


def main(args: Optional[argparse.Namespace] = None) -> None:
    """Main entry point for empty.

    Args:
        args: Parsed arguments. If None, parses from command line.
    """
    if args is None:
        parser = argparse.ArgumentParser(description="Empty directories script.")
        add_empty_arguments(parser)
        args = parser.parse_args()

    setup_logging("empty", args.log_dir)
    log_configuration(args)

    # Find empty directories
    empty_dirs = find_empty_directories(
        args.directory, args.recursive, args.include_hidden
    )

    if not empty_dirs:
        print("No empty directories found.")
        logging.info({"action": "no_empty_dirs_found"})
        return

    print(f"Found {len(empty_dirs)} empty directory(ies):")
    for d in empty_dirs:
        print(f"  {d}")

    logging.info({
        "action": "empty_dirs_found",
        "count": len(empty_dirs),
        "directories": [str(d) for d in empty_dirs],
    })

    if args.list_only:
        print("\n(Use without --list-only to remove)")
        return

    if args.dry_run:
        print("\nDry run: would remove the above directories")
        logging.info({"action": "remove_empty", "status": "dry_run"})
        return

    # Remove empty directories
    removed_count = remove_empty_directories(empty_dirs)
    print(f"\nRemoved {removed_count}/{len(empty_dirs)} directory(ies)")
    logging.info({
        "action": "remove_empty_complete",
        "removed": removed_count,
        "total": len(empty_dirs),
    })


def log_configuration(args) -> None:
    """Logs the configuration used to run the script."""
    config = {
        k: v for k, v in vars(args).items()
        if not k.startswith("_") and k not in ("func", "command")
    }
    config["action"] = "configuration"
    logging.info(config)


def find_empty_directories(
    directory: str,
    recursive: bool,
    include_hidden: bool,
) -> List[Path]:
    """Finds empty directories.

    Args:
        directory: Directory to search.
        recursive: Whether to search recursively.
        include_hidden: Whether to include hidden directories.

    Returns:
        List of paths to empty directories, sorted deepest first.
    """
    empty_dirs: List[Path] = []
    directory_path = Path(directory)

    if recursive:
        # Walk bottom-up so we can detect directories that become empty
        # after removing their empty subdirectories
        for root, dirs, files in os.walk(directory_path, topdown=False):
            root_path = Path(root)

            # Skip the root directory itself
            if root_path == directory_path:
                continue

            # Skip hidden directories if not included
            if not include_hidden and root_path.name.startswith("."):
                continue

            # Check if directory is empty (no files and no non-empty subdirs)
            if is_directory_empty(root_path, include_hidden):
                empty_dirs.append(root_path)
    else:
        for entry in os.scandir(directory_path):
            if entry.is_dir():
                dir_path = Path(entry.path)

                # Skip hidden directories if not included
                if not include_hidden and dir_path.name.startswith("."):
                    continue

                if is_directory_empty(dir_path, include_hidden):
                    empty_dirs.append(dir_path)

    # Sort by depth (deepest first) for safe removal
    empty_dirs.sort(key=lambda p: len(p.parts), reverse=True)

    return empty_dirs


def is_directory_empty(dir_path: Path, include_hidden: bool) -> bool:
    """Checks if a directory is empty.

    Args:
        dir_path: Path to the directory.
        include_hidden: Whether to consider hidden files/dirs.

    Returns:
        True if the directory is empty, False otherwise.
    """
    try:
        for entry in os.scandir(dir_path):
            # If not including hidden, skip hidden entries
            if not include_hidden and entry.name.startswith("."):
                continue
            return False
        return True
    except PermissionError:
        return False


def remove_empty_directories(empty_dirs: List[Path]) -> int:
    """Removes empty directories.

    Args:
        empty_dirs: List of paths to remove (should be sorted deepest first).

    Returns:
        Number of directories successfully removed.
    """
    removed = 0
    for dir_path in empty_dirs:
        try:
            dir_path.rmdir()
            removed += 1
            logging.info({
                "action": "remove_empty_dir",
                "status": "success",
                "path": str(dir_path),
            })
        except OSError as e:
            # Directory might not be empty anymore or have permission issues
            print(f"Error removing {dir_path}: {e}")
            logging.error({
                "action": "remove_empty_dir",
                "status": "error",
                "path": str(dir_path),
                "error": str(e),
            })

    return removed


if __name__ == "__main__":
    main()
