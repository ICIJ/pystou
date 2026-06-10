#!/usr/bin/env python3

import argparse
from pathlib import Path
from typing import Optional, List, Tuple
import logging
import os
import re
import shutil
import sqlite3

# Import modules from the package
from common.logger import setup_logging, log_configuration
from common.indexer import (
    initialize_database,
    prompt_use_existing_index,
    load_directories_from_index,
    close_database,
    update_index_after_change,
)
from common.fs_walker import collect_directories
from common.utils import group_directories, summarize_group
from common.cli import add_common_arguments
from common.validation import validate_directory_or_exit
from common.interrupt import scanning


def add_dedup_arguments(parser: argparse.ArgumentParser) -> None:
    """Adds dedup_folders-specific arguments to the parser.

    Args:
        parser: ArgumentParser to add arguments to.
    """
    add_common_arguments(parser)
    parser.add_argument(
        "-l",
        "--level",
        type=int,
        default=None,
        help="Maximum depth level for recursion (default: unlimited)",
    )
    parser.add_argument(
        "-c",
        "--default-choice",
        type=int,
        choices=[1, 2, 3],
        help="Default choice to apply to all groups (1: delete duplicates, 2: merge and delete duplicates, 3: skip)",
    )


def main(args: Optional[argparse.Namespace] = None) -> None:
    """Main entry point for dedup_folders.

    Args:
        args: Parsed arguments. If None, parses from command line.
    """
    if args is None:
        parser = argparse.ArgumentParser(description="Deduplicate folders script.")
        add_dedup_arguments(parser)
        args = parser.parse_args()

    setup_logging("dedup_folders", args.log_dir)
    log_configuration(args)
    validate_directory_or_exit(args.directory)

    conn = initialize_database(args.db_dir)
    manage_index(conn, args)

    directories = load_directories_from_index(conn)
    total_directories = len(directories)
    print(f"Total directories indexed: {total_directories:,}")
    logging.info(
        {"action": "directories_indexed", "total_directories": total_directories}
    )

    groups = group_directories(conn)
    if not groups:
        print("No duplicate directories found.")
        logging.info({"action": "no_duplicates_found"})
        close_database(conn)
        return

    with scanning("processing"):
        for group_key, dir_paths in groups.items():
            process_group(group_key, dir_paths, args, conn)

    logging.info({"action": "script_complete"})
    close_database(conn)


def manage_index(conn: sqlite3.Connection, args) -> None:
    """Manages the index, prompting the user to use existing index or rescan.

    Args:
        conn (sqlite3.Connection): SQLite database connection.
        args: Parsed command-line arguments.
    """
    db_path = os.path.join(args.db_dir, "filesystem_index.db")
    index_exists = os.path.exists(db_path)
    if index_exists:
        use_existing = prompt_use_existing_index()
        if not use_existing:
            print("Rescanning the filesystem and rebuilding the index...")
            collect_directories(conn, args.directory, args.recursive, args.level)
    else:
        print("No index file found. Scanning the filesystem...")
        collect_directories(conn, args.directory, args.recursive, args.level)


def process_group(
    group_key: Tuple[str, str], dir_paths: List[Path], args, conn: sqlite3.Connection
) -> None:
    """Processes a group of duplicate directories.

    Args:
        group_key (Tuple[str, str]): The group key (parent directory and base name).
        dir_paths (List[Path]): List of directory paths in the group.
        args: Parsed command-line arguments.
        conn (sqlite3.Connection): SQLite database connection.
    """
    parent_dir, base_name = group_key
    base_dir, duplicate_dirs = identify_base_and_duplicates(dir_paths)
    summarize_group(group_key, dir_paths, conn)
    logging.info(
        {
            "action": "found_duplicate_group",
            "parent_directory": parent_dir,
            "base_name": base_name,
            "directories": [str(d) for d in dir_paths],
            "base_directory": str(base_dir),
            "duplicate_directories": [str(d) for d in duplicate_dirs],
        }
    )
    action = prompt_user_action(args.default_choice)
    if action == "1":
        logging.info(
            {
                "action": "process_group",
                "method": "delete_duplicates",
                "group": f"{parent_dir}/{base_name}",
            }
        )
        delete_duplicates(duplicate_dirs, args.dry_run, conn)
    elif action == "2":
        logging.info(
            {
                "action": "process_group",
                "method": "merge_contents",
                "group": f"{parent_dir}/{base_name}",
            }
        )
        merge_contents(base_dir, duplicate_dirs, args.dry_run, conn)
    elif action == "3":
        print("Skipping this group.")
        logging.info(
            {
                "action": "process_group",
                "method": "skip",
                "group": f"{parent_dir}/{base_name}",
            }
        )


def identify_base_and_duplicates(dir_paths: List[Path]) -> Tuple[Path, List[Path]]:
    """Identifies the base directory and duplicates from a list of directories.

    Args:
        dir_paths (List[Path]): List of directory paths.

    Returns:
        Tuple[Path, List[Path]]: Base directory and list of duplicate directories.
    """
    suffix_pattern = re.compile(r".* \(\d+\)$")
    base_dir: Optional[Path] = None
    for dir_path in dir_paths:
        if not suffix_pattern.match(dir_path.name):
            base_dir = dir_path
            break
    if base_dir is None:
        # No base directory without suffix, pick the one with the lowest suffix number
        def get_suffix_num(dir_name: str) -> int:
            match = re.match(r".* \((\d+)\)$", dir_name)
            return int(match.group(1)) if match else float("inf")

        base_dir = min(dir_paths, key=lambda d: get_suffix_num(d.name))
    duplicate_dirs = [d for d in dir_paths if d != base_dir]
    return base_dir, duplicate_dirs


def prompt_user_action(default_choice: Optional[int]) -> str:
    """Prompts the user for action on the duplicate group.

    Args:
        default_choice (Optional[int]): Default choice to apply, if any.

    Returns:
        str: User's choice ('1', '2', or '3').
    """
    if default_choice:
        print(f"\nApplying default choice: {default_choice}")
        return str(default_choice)
    print("\nSelect an action:")
    print("1) Delete duplicate folders (keep only the base folder)")
    print("2) Merge contents into base folder, then delete duplicates")
    print("3) Skip (do nothing)")
    while True:
        choice = input("Enter your choice (1/2/3): ").strip()
        if choice in {"1", "2", "3"}:
            return choice
        else:
            print("Invalid input. Please enter 1, 2, or 3.")


def delete_duplicates(
    duplicate_dirs: List[Path], dry_run: bool, conn: sqlite3.Connection
) -> None:
    """Deletes the duplicate directories.

    Args:
        duplicate_dirs (List[Path]): List of duplicate directories to delete.
        dry_run (bool): Whether to perform a dry run.
        conn (sqlite3.Connection): SQLite database connection.
    """
    for dup_dir in duplicate_dirs:
        if dry_run:
            print(f"Dry run: would delete {dup_dir}")
            logging.info(
                {"action": "delete", "status": "dry_run", "directory": str(dup_dir)}
            )
        else:
            try:
                print(f"Deleting {dup_dir}")
                shutil.rmtree(dup_dir)
                logging.info(
                    {"action": "delete", "status": "success", "directory": str(dup_dir)}
                )
                # Update index
                update_index_after_change(conn, "delete_directory", dup_dir)
            except OSError as e:
                print(f"Error deleting {dup_dir}: {e}")
                logging.error(
                    {
                        "action": "delete",
                        "status": "error",
                        "directory": str(dup_dir),
                        "error": str(e),
                    }
                )


def merge_contents(
    base_dir: Path, duplicate_dirs: List[Path], dry_run: bool, conn: sqlite3.Connection
) -> None:
    """Merges duplicate directories into the base, preserving conflicting files.

    A duplicate directory is only deleted if every item moved without conflict;
    if any item conflicted (and was therefore skipped), the duplicate is kept so
    no data is lost.

    Args:
        base_dir (Path): Base directory.
        duplicate_dirs (List[Path]): Duplicate directories to merge.
        dry_run (bool): Whether to perform a dry run.
        conn (sqlite3.Connection): SQLite database connection.
    """
    for dup_dir in duplicate_dirs:
        had_conflict = False
        for item in os.listdir(dup_dir):
            src = dup_dir / item
            dst = base_dir / item
            if dst.exists():
                had_conflict = True
                print(f"Conflict: {dst} already exists. Keeping {src}")
                logging.info(
                    {
                        "action": "merge",
                        "status": "conflict",
                        "source": str(src),
                        "destination": str(dst),
                    }
                )
            else:
                if dry_run:
                    print(f"Dry run: would move {src} to {dst}")
                    logging.info(
                        {
                            "action": "move",
                            "status": "dry_run",
                            "source": str(src),
                            "destination": str(dst),
                        }
                    )
                else:
                    try:
                        print(f"Moving {src} to {dst}")
                        shutil.move(str(src), str(dst))
                        logging.info(
                            {
                                "action": "move",
                                "status": "success",
                                "source": str(src),
                                "destination": str(dst),
                            }
                        )
                        update_index_after_change(conn, "delete_file", src)
                        update_index_after_change(conn, "add_file", dst)
                    except OSError as e:
                        had_conflict = True  # keep the dir; the file did not move
                        print(f"Error moving {src} to {dst}: {e}")
                        logging.error(
                            {
                                "action": "move",
                                "status": "error",
                                "source": str(src),
                                "destination": str(dst),
                                "error": str(e),
                            }
                        )

        if had_conflict:
            print(f"Keeping {dup_dir} (unmerged items remain)")
            logging.info(
                {
                    "action": "delete",
                    "status": "skipped_conflict",
                    "directory": str(dup_dir),
                }
            )
            continue

        if dry_run:
            print(f"Dry run: would delete {dup_dir}")
            logging.info(
                {"action": "delete", "status": "dry_run", "directory": str(dup_dir)}
            )
        else:
            try:
                print(f"Deleting {dup_dir}")
                shutil.rmtree(dup_dir)
                logging.info(
                    {"action": "delete", "status": "success", "directory": str(dup_dir)}
                )
                update_index_after_change(conn, "delete_directory", dup_dir)
            except OSError as e:
                print(f"Error deleting {dup_dir}: {e}")
                logging.error(
                    {
                        "action": "delete",
                        "status": "error",
                        "directory": str(dup_dir),
                        "error": str(e),
                    }
                )


if __name__ == "__main__":
    main()
