#!/usr/bin/env python3
"""Empty subcommand for finding and removing empty directories."""

import argparse
import logging
import os
from pathlib import Path
from typing import Optional

from common.cli import add_common_arguments
from common.fs_walker import is_excluded_dir
from common.interrupt import scanning
from common.logger import log_configuration, setup_logging
from common.validation import validate_directory_or_exit


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

    validate_directory_or_exit(args.directory)

    # Find empty directories
    with scanning("scan"):
        empty_dirs = find_empty_directories(args.directory, args.recursive, args.include_hidden)

    if not empty_dirs:
        print("No empty directories found.")
        logging.info({"action": "no_empty_dirs_found"})
        return

    print(f"Found {len(empty_dirs)} empty directory(ies):")
    for d in empty_dirs:
        print(f"  {d}")

    logging.info(
        {
            "action": "empty_dirs_found",
            "count": len(empty_dirs),
            "directories": [str(d) for d in empty_dirs],
        }
    )

    if args.list_only:
        print("\n(Use without --list-only to remove)")
        return

    if args.dry_run:
        print("\nDry run: would remove the above directories")
        logging.info({"action": "remove_empty", "status": "dry_run"})
        return

    # Remove empty directories
    with scanning("removal"):
        removed_count, skipped_count = remove_empty_directories(empty_dirs)

    print(f"\nRemoved {removed_count}/{len(empty_dirs)} directory(ies)")
    if skipped_count > 0:
        print(f"Skipped {skipped_count} directory(ies) due to errors")
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
) -> list[Path]:
    """Finds empty directories.

    Args:
        directory: Directory to search.
        recursive: Whether to search recursively.
        include_hidden: Whether to include hidden directories.

    Returns:
        List of paths to empty directories, sorted deepest first.
    """
    empty_dirs: list[Path] = []
    directory_path = Path(directory)
    scanned = 0

    if recursive:
        # Walk bottom-up so we can detect directories that become empty
        # after removing their empty subdirectories
        # followlinks=False prevents infinite loops from symlink cycles
        for root, _dirs, _files in os.walk(directory_path, topdown=False, followlinks=False):
            root_path = Path(root)
            scanned += 1

            # Progress indicator every 1000 directories
            if scanned % 1000 == 0:
                print(f"Scanned {scanned} directories...", end="\r")

            # Skip the root directory itself
            if root_path == directory_path:
                continue

            # Skip symlinks
            if root_path.is_symlink():
                continue

            # Skip the trash directory and anything inside it. Bottom-up walks
            # cannot prune via dirs[:], so guard at the collection point.
            if any(is_excluded_dir(p) for p in root_path.parts):
                continue

            # Skip hidden directories if not included
            if not include_hidden and root_path.name.startswith("."):
                continue

            # Check if directory is empty (no files and no non-empty subdirs)
            if is_directory_empty(root_path, include_hidden):
                empty_dirs.append(root_path)
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

                    if is_directory_empty(dir_path, include_hidden):
                        empty_dirs.append(dir_path)
        except PermissionError as e:
            print(f"Permission denied: {directory_path}")
            logging.warning({"action": "scan_error", "path": str(directory_path), "error": str(e)})

    if scanned >= 1000:
        print(f"Scanned {scanned} directories.    ")  # Clear progress line

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
        with os.scandir(dir_path) as entries:
            for entry in entries:
                # Skip symlinks when checking contents
                if entry.is_symlink():
                    continue
                # If not including hidden, skip hidden entries
                if not include_hidden and entry.name.startswith("."):
                    continue
                return False
        return True
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
    total = len(empty_dirs)

    for i, dir_path in enumerate(empty_dirs, 1):
        # Progress indicator
        if total > 10 and i % 10 == 0:
            print(f"Removing {i}/{total}...", end="\r")

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
            print(f"Permission denied: {dir_path}")
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
            if "not empty" in str(e).lower() or e.errno == 39:  # ENOTEMPTY
                logging.warning(
                    {
                        "action": "remove_empty_dir",
                        "status": "not_empty",
                        "path": str(dir_path),
                    }
                )
            else:
                print(f"Error removing {dir_path}: {e}")
                logging.error(
                    {
                        "action": "remove_empty_dir",
                        "status": "error",
                        "path": str(dir_path),
                        "error": str(e),
                    }
                )
            skipped += 1

    if total > 10:
        print(f"Removed {removed}/{total} directories.    ")  # Clear progress line

    return removed, skipped


if __name__ == "__main__":
    main()
