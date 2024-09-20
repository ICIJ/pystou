#!/usr/bin/env python3

import os
import logging
from pathlib import Path
from typing import Optional

# Import common modules
from common.logger import setup_logging
from common.utils import get_archive_files, extract_archive
from common.indexer import (
    initialize_database,
    prompt_use_existing_index,
    close_database,
    update_index_after_change,
)
from common.fs_walker import collect_directories
from common.cli import parse_arguments


def main():
    parser = parse_arguments("unarchive")
    parser.add_argument(
        "-c",
        "--default-choice",
        type=int,
        choices=[1, 2],
        help="Default choice to apply to all archives (1: extract, 2: skip)",
    )
    parser.add_argument(
        "-dc",
        "--default-delete-choice",
        type=int,
        choices=[1, 2],
        help="Default choice to apply when prompted to delete after extraction (1: delete, 2: keep)",
    )
    args = parser.parse_args()
    setup_logging("unarchive", args.log_dir)
    log_configuration(args)

    conn = initialize_database(args.db_dir)
    manage_index(conn, args)

    archive_files = get_archive_files(args.directory, args.recursive)
    total_archives = len(archive_files)
    print(f"Found {total_archives} archive files.")
    logging.info({"action": "archives_found", "total_archives": total_archives})

    if total_archives == 0:
        print("No archive files found.")
        logging.info({"action": "no_archives_found"})
        close_database(conn)
        return

    for archive_file in archive_files:
        process_archive(archive_file, args, conn)

    logging.info({"action": "script_complete"})
    close_database(conn)


def log_configuration(args):
    """Logs the configuration used to run the script."""
    config = vars(args)
    config["action"] = "configuration"
    logging.info(config)


def manage_index(conn, args):
    """Manages the index, prompting the user to use existing index or rescan."""
    db_path = os.path.join(args.db_dir, "filesystem_index.db")
    index_exists = os.path.exists(db_path)
    if index_exists:
        use_existing = prompt_use_existing_index()
        if not use_existing:
            print("Rescanning the filesystem and rebuilding the index...")
            collect_directories(conn, args.directory, args.recursive)
    else:
        print("No index file found. Scanning the filesystem...")
        collect_directories(conn, args.directory, args.recursive)


def process_archive(archive_file: Path, args, conn) -> None:
    """Processes a single archive file.

    Args:
        archive_file (Path): The archive file to process.
        args: Parsed command-line arguments.
        conn: SQLite database connection.
    """
    print(f"\nFound archive: {archive_file}")
    action = prompt_user_action(archive_file, args.default_choice)
    if action == "1":
        extract_and_update_index(archive_file, args, conn)
    elif action == "2":
        print(f"Skipping archive: {archive_file}")
        logging.info({"action": "skip_archive", "archive": str(archive_file)})


def prompt_user_action(archive_file: Path, default_choice: Optional[int]) -> str:
    """Prompts the user for action on the given archive file.

    Args:
        archive_file (Path): The archive file in question.
        default_choice (Optional[int]): The default choice to apply, if any.

    Returns:
        str: The user's choice ('1' or '2').
    """
    if default_choice:
        print(f"Applying default choice {default_choice} for {archive_file}")
        return str(default_choice)

    print("\nSelect an action:")
    print("1) Extract the archive")
    print("2) Skip (do nothing)")
    while True:
        choice = input("Enter your choice (1/2): ").strip()
        if choice in {"1", "2"}:
            return choice
        else:
            print("Invalid input. Please enter 1 or 2.")


def prompt_delete_action(
    archive_file: Path, default_delete_choice: Optional[int]
) -> str:
    """Prompts the user whether to delete the archive after extraction.

    Args:
        archive_file (Path): The archive file that was extracted.
        default_delete_choice (Optional[int]): The default choice to apply, if any.

    Returns:
        str: The user's choice ('1' or '2').
    """
    if default_delete_choice:
        print(
            f"Applying default delete choice {default_delete_choice} for {archive_file}"
        )
        return str(default_delete_choice)

    print("\nExtraction complete.")
    print("Do you want to delete the archive file?")
    print("1) Yes, delete the archive")
    print("2) No, keep the archive")
    while True:
        choice = input("Enter your choice (1/2): ").strip()
        if choice in {"1", "2"}:
            return choice
        else:
            print("Invalid input. Please enter 1 or 2.")


def extract_and_update_index(archive_file: Path, args, conn) -> None:
    """Extracts the archive and updates the index.

    Args:
        archive_file (Path): The archive file to extract.
        args: Parsed command-line arguments.
        conn: SQLite database connection.
    """
    if args.dry_run:
        print(f"Dry run: would extract {archive_file}")
        logging.info(
            {"action": "extract", "status": "dry_run", "archive": str(archive_file)}
        )
    else:
        success = extract_archive(archive_file)
        if success:
            logging.info(
                {"action": "extract", "status": "success", "archive": str(archive_file)}
            )
            # Update index with new files/directories
            update_index_after_extraction(conn, archive_file.parent)
            # Prompt to delete the archive
            delete_action = prompt_delete_action(
                archive_file, args.default_delete_choice
            )
            if delete_action == "1":
                delete_archive_file(archive_file, conn, args.dry_run)
            else:
                print(f"Keeping archive: {archive_file}")
                logging.info({"action": "keep_archive", "archive": str(archive_file)})
        else:
            logging.error(
                {"action": "extract", "status": "error", "archive": str(archive_file)}
            )


def update_index_after_extraction(conn, directory: Path) -> None:
    """Updates the index after extraction of an archive.

    Args:
        conn: SQLite database connection.
        directory (Path): The directory where the archive was extracted.
    """
    # Re-scan the directory where the archive was extracted
    collect_directories(conn, directory, recursive=False)


def delete_archive_file(archive_file: Path, conn, dry_run: bool) -> None:
    """Deletes the archive file and updates the index.

    Args:
        archive_file (Path): The archive file to delete.
        conn: SQLite database connection.
        dry_run (bool): Whether to perform a dry run.
    """
    if dry_run:
        print(f"Dry run: would delete archive: {archive_file}")
        logging.info(
            {
                "action": "delete_archive",
                "status": "dry_run",
                "archive": str(archive_file),
            }
        )
    else:
        try:
            print(f"Deleting archive: {archive_file}")
            archive_file.unlink()
            logging.info(
                {
                    "action": "delete_archive",
                    "status": "success",
                    "archive": str(archive_file),
                }
            )
            # Update index
            update_index_after_change(conn, "delete_file", archive_file)
        except Exception as e:
            print(f"Error deleting archive {archive_file}: {e}")
            logging.error(
                {
                    "action": "delete_archive",
                    "status": "error",
                    "archive": str(archive_file),
                    "error": str(e),
                }
            )


if __name__ == "__main__":
    main()
