#!/usr/bin/env python3

import argparse
import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional

# Import common modules
from common.logger import setup_logging
from common.utils import get_archive_files, extract_archive, get_split_archive_parts
from common.indexer import (
    initialize_database,
    prompt_use_existing_index,
    close_database,
    update_index_after_change,
)
from common.fs_walker import collect_directories
from common.cli import add_common_arguments


def add_extract_arguments(parser: argparse.ArgumentParser) -> None:
    """Adds extract-specific arguments to the parser.

    Args:
        parser: ArgumentParser to add arguments to.
    """
    add_common_arguments(parser)
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
    parser.add_argument(
        "-p",
        "--parallel",
        type=int,
        default=1,
        metavar="N",
        help="Number of parallel extraction workers (default: 1, requires -c flag)",
    )
    parser.add_argument(
        "-N",
        "--nested",
        action="store_true",
        help="Recursively extract archives found inside extracted content",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=10,
        metavar="N",
        help="Maximum nesting depth for --nested (default: 10)",
    )
    parser.add_argument(
        "-t",
        "--type",
        action="append",
        dest="types",
        metavar="TYPE",
        help="Only extract archives of this type (e.g., pst, zip, tar.gz). Can be used multiple times.",
    )


def main(args: Optional[argparse.Namespace] = None) -> None:
    """Main entry point for extract.

    Args:
        args: Parsed arguments. If None, parses from command line.
    """
    if args is None:
        parser = argparse.ArgumentParser(description="Extract archives script.")
        add_extract_arguments(parser)
        args = parser.parse_args()

    setup_logging("extract", args.log_dir)
    log_configuration(args)

    conn = initialize_database(args.db_dir)
    manage_index(conn, args)

    archive_files = get_archive_files(args.directory, args.recursive, args.types)
    total_archives = len(archive_files)
    print(f"Found {total_archives} archive files.")
    logging.info({"action": "archives_found", "total_archives": total_archives})

    if total_archives == 0:
        print("No archive files found.")
        logging.info({"action": "no_archives_found"})
        close_database(conn)
        return

    # Use parallel extraction when enabled and in automatic mode
    if args.parallel > 1 and args.default_choice == 1:
        process_archives_parallel(archive_files, args, conn)
    else:
        for archive_file in archive_files:
            process_archive(archive_file, args, conn)

    logging.info({"action": "script_complete"})
    close_database(conn)


def log_configuration(args):
    """Logs the configuration used to run the script."""
    config = {
        k: v for k, v in vars(args).items()
        if not k.startswith("_") and k not in ("func", "command")
    }
    config["action"] = "configuration"
    logging.info(config)


def process_archives_parallel(archive_files: List[Path], args, conn) -> None:
    """Processes multiple archives in parallel.

    Args:
        archive_files (List[Path]): List of archive files to process.
        args: Parsed command-line arguments.
        conn: SQLite database connection.
    """
    print(f"Extracting {len(archive_files)} archives with {args.parallel} workers...")

    # Extract archives in parallel
    results = []
    with ThreadPoolExecutor(max_workers=args.parallel) as executor:
        future_to_archive = {
            executor.submit(extract_archive, archive): archive
            for archive in archive_files
        }
        for future in as_completed(future_to_archive):
            archive = future_to_archive[future]
            try:
                success = future.result()
                results.append((archive, success))
                status = "success" if success else "failed"
                print(f"Extracted ({status}): {archive}")
            except Exception as e:
                results.append((archive, False))
                print(f"Error extracting {archive}: {e}")
                logging.error(
                    {"action": "extract", "status": "error", "archive": str(archive), "error": str(e)}
                )

    # Update index and handle deletion sequentially (database operations)
    successful = [(archive, success) for archive, success in results if success]
    print(f"\nSuccessfully extracted {len(successful)}/{len(archive_files)} archives.")

    for archive, _ in successful:
        logging.info({"action": "extract", "status": "success", "archive": str(archive)})
        update_index_after_extraction(conn, archive.parent)

        if args.default_delete_choice == 1:
            delete_archive_file(archive, conn, args.dry_run)
        elif args.default_delete_choice == 2:
            print(f"Keeping archive: {archive}")
            logging.info({"action": "keep_archive", "archive": str(archive)})
        else:
            # Prompt for each successful extraction
            delete_action = prompt_delete_action(archive, None)
            if delete_action == "1":
                delete_archive_file(archive, conn, args.dry_run)
            else:
                print(f"Keeping archive: {archive}")
                logging.info({"action": "keep_archive", "archive": str(archive)})


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


def extract_and_update_index(
    archive_file: Path, args, conn, depth: int = 0
) -> None:
    """Extracts the archive and updates the index.

    Args:
        archive_file (Path): The archive file to extract.
        args: Parsed command-line arguments.
        conn: SQLite database connection.
        depth (int): Current nesting depth for nested extraction.
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

            # Handle nested extraction if enabled
            if args.nested and depth < args.max_depth:
                process_nested_archives(archive_file.parent, args, conn, depth + 1)

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


def process_nested_archives(
    directory: Path, args, conn, depth: int
) -> None:
    """Processes nested archives found in the extracted directory.

    Args:
        directory (Path): Directory to scan for nested archives.
        args: Parsed command-line arguments.
        conn: SQLite database connection.
        depth (int): Current nesting depth.
    """
    nested_archives = get_archive_files(directory, recursive=True)
    if not nested_archives:
        return

    print(f"\n[Depth {depth}] Found {len(nested_archives)} nested archive(s)")
    logging.info({
        "action": "nested_archives_found",
        "directory": str(directory),
        "count": len(nested_archives),
        "depth": depth,
    })

    for archive in nested_archives:
        print(f"[Depth {depth}] Extracting nested archive: {archive}")
        extract_and_update_index(archive, args, conn, depth)


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

    For split archives, also deletes all split parts (.z01, .z02, etc.).

    Args:
        archive_file (Path): The archive file to delete.
        conn: SQLite database connection.
        dry_run (bool): Whether to perform a dry run.
    """
    # Get all files to delete (includes split parts if applicable)
    split_parts = get_split_archive_parts(archive_file)
    files_to_delete = split_parts if split_parts else [archive_file]

    if dry_run:
        for f in files_to_delete:
            print(f"Dry run: would delete archive: {f}")
        logging.info(
            {
                "action": "delete_archive",
                "status": "dry_run",
                "archive": str(archive_file),
                "parts_count": len(files_to_delete),
            }
        )
    else:
        for f in files_to_delete:
            try:
                print(f"Deleting archive: {f}")
                f.unlink()
                logging.info(
                    {
                        "action": "delete_archive",
                        "status": "success",
                        "archive": str(f),
                    }
                )
                # Update index
                update_index_after_change(conn, "delete_file", f)
            except Exception as e:
                print(f"Error deleting archive {f}: {e}")
                logging.error(
                    {
                        "action": "delete_archive",
                        "status": "error",
                        "archive": str(f),
                        "error": str(e),
                    }
                )


if __name__ == "__main__":
    main()
