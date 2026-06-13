#!/usr/bin/env python3

import argparse
import logging
import os
import shlex
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
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
    add_common_arguments,
)
from common.fs_walker import collect_directories
from common.indexer import (
    close_database,
    index_has_data,
    initialize_database,
    prompt_use_existing_index,
    update_index_after_change,
)
from common.interrupt import scanning

# Import common modules
from common.logger import log_configuration, setup_logging
from common.safe_ops import verify_then_delete
from common.utils import extract_archive, get_archive_files, get_split_archive_parts
from common.validation import validate_directory_or_exit


class ExtractAction(str, Enum):
    extract = "extract"
    skip = "skip"


def extract_command(
    directory: DirectoryArg = ".",
    recursive: RecursiveOpt = False,
    action: Annotated[
        Optional[ExtractAction],
        typer.Option("--action", help="extract|skip; omit to prompt per archive."),
    ] = None,
    remove_archives: Annotated[
        bool,
        typer.Option(
            "--remove-archives/--keep-archives",
            help="Remove (quarantine) archives after success; default keep.",
        ),
    ] = False,
    parallel: Annotated[
        int, typer.Option("-p", "--parallel", help="Parallel extraction workers.")
    ] = 1,
    nested: Annotated[
        bool, typer.Option("--nested", help="Recursively extract nested archives.")
    ] = False,
    max_depth: Annotated[
        int, typer.Option("--max-depth", help="Max nesting depth for --nested.")
    ] = 10,
    types: Annotated[
        Optional[list[str]], typer.Option("--type", help="Only this archive type (repeatable).")
    ] = None,
    dry_run: DryRunOpt = False,
    hard_delete: HardDeleteOpt = False,
    trash_dir: TrashDirOpt = None,
    log_dir: LogDirOpt = ".",
    db_dir: DbDirOpt = ".",
) -> None:
    """Extract archives (zip/tar/gz/zst/pst); quarantines archives only on request."""
    setup_logging("extract", log_dir)
    logging.info(
        {
            "action": "configuration",
            "command": "extract",
            "directory": directory,
            "recursive": recursive,
            "extract_action": action.value if action is not None else None,
            "remove_archives": remove_archives,
            "parallel": parallel,
            "nested": nested,
            "max_depth": max_depth,
            "types": types,
            "dry_run": dry_run,
            "hard_delete": hard_delete,
        }
    )
    validate_directory_or_exit(directory)

    db_path = os.path.join(db_dir, "filesystem_index.db")
    index_existed = os.path.exists(db_path)
    conn = initialize_database(db_dir)

    def rescan() -> None:
        with console.progress() as p:
            task = p.add_task("Scanning", total=None)
            collect_directories(
                conn,
                directory,
                recursive,
                progress_cb=lambda d, f: p.update(
                    task, description=f"Scanning  dirs {d:,}  files {f:,}"
                ),
            )

    if index_existed and index_has_data(conn):
        if not console.confirm("Use the existing index?", default=True):
            rescan()
    else:
        rescan()

    archives = get_archive_files(directory, recursive, types)
    logging.info({"action": "archives_found", "total_archives": len(archives)})
    if not archives:
        console.status("No archive files found.")
        logging.info({"action": "no_archives_found"})
        close_database(conn)
        return
    console.status(f"Found {len(archives)} archive(s).")

    # Resolve per-archive action (prompt once per archive when --action omitted).
    to_extract: list[Path] = []
    for archive in archives:
        if action is not None:
            resolved = action
        else:
            chosen = console.prompt_choice(
                f"Action for {archive.name}", ["extract", "skip"], default="extract"
            )
            resolved = ExtractAction(chosen)
        if resolved is ExtractAction.extract:
            to_extract.append(archive)
        else:
            console.status(f"Skipping archive: {archive}")
            logging.info({"action": "skip_archive", "archive": str(archive)})

    if not to_extract:
        close_database(conn)
        return

    if parallel > 1 and not dry_run:
        _extract_parallel(
            to_extract,
            conn,
            parallel,
            directory,
            remove_archives=remove_archives,
            nested=nested,
            max_depth=max_depth,
            types=types,
            hard_delete=hard_delete,
            trash_dir=trash_dir,
        )
    else:
        with console.progress() as p:
            task = p.add_task("Extracting", total=len(to_extract))
            for archive in to_extract:
                p.update(task, description=f"Extracting {archive.name}")
                _extract_one(
                    archive,
                    conn,
                    directory,
                    dry_run=dry_run,
                    remove_archives=remove_archives,
                    nested=nested,
                    max_depth=max_depth,
                    types=types,
                    hard_delete=hard_delete,
                    trash_dir=trash_dir,
                )
                p.advance(task)

    logging.info({"action": "script_complete"})
    close_database(conn)


def _extract_one(
    archive: Path,
    conn,
    op_root: str,
    *,
    dry_run: bool,
    remove_archives: bool,
    nested: bool,
    max_depth: int,
    types: Optional[list[str]],
    hard_delete: bool,
    trash_dir: Optional[str],
    depth: int = 0,
) -> None:
    """Extracts a single archive, updates the index, handles nesting and removal."""
    if dry_run:
        console.status(f"Dry run: would extract {archive}")
        logging.info({"action": "extract", "status": "dry_run", "archive": str(archive)})
        return

    success = extract_archive(archive)
    if not success:
        console.error(f"Failed to extract {archive}")
        logging.error({"action": "extract", "status": "error", "archive": str(archive)})
        return

    logging.info({"action": "extract", "status": "success", "archive": str(archive)})
    update_index_after_extraction(conn, archive.parent)

    if nested and depth < max_depth:
        _extract_nested(
            archive.parent,
            conn,
            op_root,
            remove_archives=remove_archives,
            max_depth=max_depth,
            types=types,
            hard_delete=hard_delete,
            trash_dir=trash_dir,
            depth=depth + 1,
        )

    if remove_archives:
        delete_archive_file(
            archive,
            conn,
            dry_run,
            op_root,
            hard_delete=hard_delete,
            trash_dir=trash_dir,
        )
    else:
        console.status(f"Keeping archive: {archive}")
        logging.info({"action": "keep_archive", "archive": str(archive)})


def _extract_nested(
    directory: Path,
    conn,
    op_root: str,
    *,
    remove_archives: bool,
    max_depth: int,
    types: Optional[list[str]],
    hard_delete: bool,
    trash_dir: Optional[str],
    depth: int,
) -> None:
    """Scans a freshly-extracted directory for nested archives and extracts them."""
    nested_archives = get_archive_files(directory, recursive=True, filter_types=types)
    if not nested_archives:
        return
    console.status(f"[Depth {depth}] Found {len(nested_archives)} nested archive(s)")
    logging.info(
        {
            "action": "nested_archives_found",
            "directory": str(directory),
            "count": len(nested_archives),
            "depth": depth,
        }
    )
    for archive in nested_archives:
        _extract_one(
            archive,
            conn,
            op_root,
            dry_run=False,
            remove_archives=remove_archives,
            nested=True,
            max_depth=max_depth,
            types=types,
            hard_delete=hard_delete,
            trash_dir=trash_dir,
            depth=depth,
        )


def _extract_parallel(
    archives: list[Path],
    conn,
    workers: int,
    op_root: str,
    *,
    remove_archives: bool,
    nested: bool,
    max_depth: int,
    types: Optional[list[str]],
    hard_delete: bool,
    trash_dir: Optional[str],
) -> None:
    """Extracts archives concurrently, then runs index-update + removal sequentially.

    Mirrors the legacy ``process_archives_parallel``: extraction (CPU/IO bound,
    thread-safe) is parallelised, while the SQLite index mutations and removals
    are serialised because the connection is single-threaded.
    """
    console.status(f"Extracting {len(archives)} archive(s) with {workers} workers...")
    results: list[tuple[Path, bool]] = []
    with console.progress() as p:
        task = p.add_task("Extracting", total=len(archives))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_archive = {
                executor.submit(extract_archive, archive): archive for archive in archives
            }
            for future in as_completed(future_to_archive):
                archive = future_to_archive[future]
                p.update(task, description=f"Extracting {archive.name}")
                try:
                    success = future.result()
                except Exception as e:  # surface and continue
                    success = False
                    console.error(f"Error extracting {archive}: {e}")
                    logging.error(
                        {
                            "action": "extract",
                            "status": "error",
                            "archive": str(archive),
                            "error": str(e),
                        }
                    )
                results.append((archive, success))
                p.advance(task)

    # Sequential phase: index updates, nested extraction, and removals.
    for archive, success in results:
        if not success:
            console.error(f"Failed to extract {archive}")
            logging.error({"action": "extract", "status": "error", "archive": str(archive)})
            continue
        logging.info({"action": "extract", "status": "success", "archive": str(archive)})
        update_index_after_extraction(conn, archive.parent)

        if nested:
            _extract_nested(
                archive.parent,
                conn,
                op_root,
                remove_archives=remove_archives,
                max_depth=max_depth,
                types=types,
                hard_delete=hard_delete,
                trash_dir=trash_dir,
                depth=1,
            )

        if remove_archives:
            verify_then_delete(
                archive,
                success,
                lambda a=archive: delete_archive_file(
                    a,
                    conn,
                    False,
                    op_root,
                    hard_delete=hard_delete,
                    trash_dir=trash_dir,
                ),
            )
        else:
            console.status(f"Keeping archive: {archive}")
            logging.info({"action": "keep_archive", "archive": str(archive)})


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

    validate_directory_or_exit(args.directory)

    db_path = os.path.join(args.db_dir, "filesystem_index.db")
    index_existed = os.path.exists(db_path)
    conn = initialize_database(args.db_dir)
    manage_index(conn, args, index_existed)

    with scanning("scan"):
        archive_files = get_archive_files(args.directory, args.recursive, args.types)
    total_archives = len(archive_files)
    print(f"Found {total_archives} archive files.")
    logging.info({"action": "archives_found", "total_archives": total_archives})

    if total_archives == 0:
        print("No archive files found.")
        logging.info({"action": "no_archives_found"})
        close_database(conn)
        return

    with scanning("extraction"):
        if args.parallel > 1 and args.default_choice == 1:
            process_archives_parallel(archive_files, args, conn)
        else:
            for archive_file in archive_files:
                process_archive(archive_file, args, conn)

    logging.info({"action": "script_complete"})
    close_database(conn)


def process_archives_parallel(archive_files: list[Path], args, conn) -> None:
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
            executor.submit(extract_archive, archive): archive for archive in archive_files
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
                    {
                        "action": "extract",
                        "status": "error",
                        "archive": str(archive),
                        "error": str(e),
                    }
                )

    # Update index and handle deletion sequentially (database operations)
    successful = [(archive, success) for archive, success in results if success]
    print(f"\nSuccessfully extracted {len(successful)}/{len(archive_files)} archives.")

    for archive, success in results:
        if success:
            logging.info({"action": "extract", "status": "success", "archive": str(archive)})
            update_index_after_extraction(conn, archive.parent)

        if args.default_delete_choice == 1:
            verify_then_delete(
                archive,
                success,
                lambda a=archive: delete_archive_file(
                    a,
                    conn,
                    args.dry_run,
                    args.directory,
                    hard_delete=args.hard_delete,
                    trash_dir=args.trash_dir,
                ),
            )
        elif args.default_delete_choice == 2:
            print(f"Keeping archive: {archive}")
            logging.info({"action": "keep_archive", "archive": str(archive)})
        else:
            if success:
                delete_action = prompt_delete_action(archive, None)
                if delete_action == "1":
                    delete_archive_file(
                        archive,
                        conn,
                        args.dry_run,
                        args.directory,
                        hard_delete=args.hard_delete,
                        trash_dir=args.trash_dir,
                    )
                else:
                    print(f"Keeping archive: {archive}")
                    logging.info({"action": "keep_archive", "archive": str(archive)})
            else:
                print(f"Keeping archive: {archive}")
                logging.info({"action": "keep_archive", "archive": str(archive)})


def manage_index(conn, args, index_existed: bool) -> None:
    """Manages the index, prompting the user to use existing index or rescan."""
    if index_existed and index_has_data(conn):
        use_existing = prompt_use_existing_index()
        if not use_existing:
            print("Rescanning the filesystem and rebuilding the index...")
            collect_directories(conn, args.directory, args.recursive)
    elif index_existed:
        print("Empty index found. Rescanning the filesystem...")
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


def prompt_delete_action(archive_file: Path, default_delete_choice: Optional[int]) -> str:
    """Prompts the user whether to delete the archive after extraction.

    Args:
        archive_file (Path): The archive file that was extracted.
        default_delete_choice (Optional[int]): The default choice to apply, if any.

    Returns:
        str: The user's choice ('1' or '2').
    """
    if default_delete_choice:
        print(f"Applying default delete choice {default_delete_choice} for {archive_file}")
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


def extract_and_update_index(archive_file: Path, args, conn, depth: int = 0) -> None:
    """Extracts the archive and updates the index.

    Args:
        archive_file (Path): The archive file to extract.
        args: Parsed command-line arguments.
        conn: SQLite database connection.
        depth (int): Current nesting depth for nested extraction.
    """
    if args.dry_run:
        print(f"Dry run: would extract {archive_file}")
        logging.info({"action": "extract", "status": "dry_run", "archive": str(archive_file)})
    else:
        success = extract_archive(archive_file)
        if success:
            logging.info({"action": "extract", "status": "success", "archive": str(archive_file)})
            # Update index with new files/directories
            update_index_after_extraction(conn, archive_file.parent)

            # Handle nested extraction if enabled
            if args.nested and depth < args.max_depth:
                process_nested_archives(archive_file.parent, args, conn, depth + 1)

            # Prompt to delete the archive
            delete_action = prompt_delete_action(archive_file, args.default_delete_choice)
            if delete_action == "1":
                delete_archive_file(
                    archive_file,
                    conn,
                    args.dry_run,
                    args.directory,
                    hard_delete=args.hard_delete,
                    trash_dir=args.trash_dir,
                )
            else:
                print(f"Keeping archive: {archive_file}")
                logging.info({"action": "keep_archive", "archive": str(archive_file)})
        else:
            logging.error({"action": "extract", "status": "error", "archive": str(archive_file)})


def process_nested_archives(directory: Path, args, conn, depth: int) -> None:
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
    logging.info(
        {
            "action": "nested_archives_found",
            "directory": str(directory),
            "count": len(nested_archives),
            "depth": depth,
        }
    )

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


def delete_archive_file(
    archive_file: Path,
    conn,
    dry_run: bool,
    op_root: str = ".",
    *,
    hard_delete: bool = False,
    trash_dir: Optional[str] = None,
) -> None:
    """Removes the archive (and split parts), quarantining by default.

    Args:
        archive_file (Path): The archive file to remove.
        conn: SQLite database connection.
        dry_run (bool): Whether to perform a dry run.
        op_root (str): Directory hosting the trash.
        hard_delete (bool): If True, permanently delete instead of quarantining.
        trash_dir (Optional[str]): Optional trash location override.
    """
    split_parts = get_split_archive_parts(archive_file)
    files_to_delete = split_parts if split_parts else [archive_file]

    if dry_run:
        for f in files_to_delete:
            verb = "delete" if hard_delete else "quarantine"
            print(f"Dry run: would {verb} archive: {f}")
        logging.info(
            {
                "action": "delete_archive",
                "status": "dry_run",
                "archive": str(archive_file),
                "parts_count": len(files_to_delete),
            }
        )
        return

    if not hard_delete:
        try:
            trash.quarantine(
                files_to_delete,
                op_root,
                operation="extract",
                command=shlex.join(sys.argv),
                trash_dir=trash_dir,
            )
            for f in files_to_delete:
                print(f"Quarantined archive: {f}")
                logging.info({"action": "delete_archive", "status": "success", "archive": str(f)})
                update_index_after_change(conn, "delete_file", f)
        except (trash.CrossDeviceTrashError, trash.TrashUnavailableError) as e:
            print(f"Error: {e}")
            logging.error(
                {
                    "action": "delete_archive",
                    "status": "trash_error",
                    "archive": str(archive_file),
                    "error": str(e),
                }
            )
        return

    for f in files_to_delete:
        try:
            print(f"Deleting archive: {f}")
            f.unlink()
            logging.info({"action": "delete_archive", "status": "success", "archive": str(f)})
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
