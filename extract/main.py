#!/usr/bin/env python3

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
)
from common.fs_walker import collect_directories
from common.indexer import (
    close_database,
    index_has_data,
    initialize_database,
    update_index_after_change,
)
from common.logger import setup_logging
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
            console.status(f"Dry run: would {verb} archive: {f}")
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
                console.status(f"Quarantined archive: {f}")
                logging.info({"action": "delete_archive", "status": "success", "archive": str(f)})
                update_index_after_change(conn, "delete_file", f)
        except (trash.CrossDeviceTrashError, trash.TrashUnavailableError) as e:
            console.error(str(e))
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
            console.status(f"Deleting archive: {f}")
            f.unlink()
            logging.info({"action": "delete_archive", "status": "success", "archive": str(f)})
            update_index_after_change(conn, "delete_file", f)
        except Exception as e:
            console.error(f"Error deleting archive {f}: {e}")
            logging.error(
                {
                    "action": "delete_archive",
                    "status": "error",
                    "archive": str(f),
                    "error": str(e),
                }
            )
