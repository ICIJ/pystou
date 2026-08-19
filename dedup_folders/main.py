#!/usr/bin/env python3

import logging
import os
import re
import shlex
import shutil
import sqlite3
import sys
from enum import Enum
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.tree import Tree

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
from common.fs_walker import ScanContext, collect_directories, scan_tree
from common.indexer import (
    close_database,
    index_has_data,
    initialize_database,
    update_index_after_change,
)
from common.logger import setup_logging
from common.utils import group_directories
from common.validation import validate_directory_or_exit


class DedupAction(str, Enum):
    delete = "delete"
    merge = "merge"
    skip = "skip"


def dedup_command(
    directory: DirectoryArg = ".",
    recursive: RecursiveOpt = False,
    level: Annotated[
        Optional[int], typer.Option("-l", "--level", help="Max recursion depth.")
    ] = None,
    action: Annotated[
        Optional[DedupAction],
        typer.Option("--action", help="delete|merge|skip; omit to prompt per group."),
    ] = None,
    dry_run: DryRunOpt = False,
    hard_delete: HardDeleteOpt = False,
    trash_dir: TrashDirOpt = None,
    log_dir: LogDirOpt = ".",
    db_dir: DbDirOpt = ".",
) -> None:
    """Find duplicate folders (e.g. "data" / "data (1)") and delete, merge, or skip."""
    setup_logging("dedup_folders", log_dir)
    logging.info(
        {
            "action": "configuration",
            "command": "dedup",
            "directory": directory,
            "recursive": recursive,
            "level": level,
            "dedup_action": action.value if action is not None else None,
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
                level,
                progress_cb=lambda d, f: p.update(
                    task, description=f"Scanning  dirs {d:,}  files {f:,}"
                ),
            )

    if index_existed and index_has_data(conn):
        if not console.confirm("Use the existing index?", default=True):
            rescan()
    else:
        rescan()

    groups = group_directories(conn, directory)
    if not groups:
        console.status("No duplicate directories found.")
        logging.info({"action": "no_duplicates_found"})
        close_database(conn)
        return

    for group_key, dir_paths in groups.items():
        parent_dir, base_name = group_key
        base_dir, duplicate_dirs = identify_base_and_duplicates(dir_paths)

        tree = Tree(str(base_dir))
        for dup in duplicate_dirs:
            tree.add(str(dup))
        console.print_tree(tree)

        logging.info(
            {
                "action": "found_duplicate_group",
                "parent_directory": parent_dir,
                "base_name": base_name,
                "base_directory": str(base_dir),
                "duplicate_directories": [str(d) for d in duplicate_dirs],
            }
        )

        if action is not None:
            action_val = action
        else:
            chosen = console.prompt_choice(
                "Action for this group", ["delete", "merge", "skip"], default="skip"
            )
            action_val = DedupAction(chosen)

        if action_val is DedupAction.delete:
            logging.info(
                {
                    "action": "process_group",
                    "method": "delete_duplicates",
                    "group": f"{parent_dir}/{base_name}",
                }
            )
            delete_duplicates(
                duplicate_dirs,
                dry_run,
                conn,
                directory,
                hard_delete=hard_delete,
                trash_dir=trash_dir,
            )
        elif action_val is DedupAction.merge:
            logging.info(
                {
                    "action": "process_group",
                    "method": "merge_contents",
                    "group": f"{parent_dir}/{base_name}",
                }
            )
            merge_contents(
                base_dir,
                duplicate_dirs,
                dry_run,
                conn,
                directory,
                hard_delete=hard_delete,
                trash_dir=trash_dir,
            )
        else:
            console.status("Skipping group.")
            logging.info(
                {
                    "action": "process_group",
                    "method": "skip",
                    "group": f"{parent_dir}/{base_name}",
                }
            )

    logging.info({"action": "script_complete"})
    close_database(conn)


def identify_base_and_duplicates(dir_paths: list[Path]) -> tuple[Path, list[Path]]:
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


def _remove_or_quarantine_dir(
    dup_dir: Path,
    conn: sqlite3.Connection,
    op_root: str,
    hard_delete: bool,
    trash_dir: Optional[str],
) -> None:
    """Removes one duplicate dir (quarantine by default, hard-delete on request),
    then updates the index. Errors are logged, not raised."""
    try:
        if hard_delete:
            console.status(f"Deleting {dup_dir}")
            shutil.rmtree(dup_dir)
        else:
            console.status(f"Quarantining {dup_dir}")
            trash.quarantine(
                [dup_dir],
                op_root,
                operation="dedup",
                command=shlex.join(sys.argv),
                trash_dir=trash_dir,
            )
        logging.info({"action": "delete", "status": "success", "directory": str(dup_dir)})
        update_index_after_change(conn, "delete_directory", dup_dir)
    except (trash.CrossDeviceTrashError, trash.TrashUnavailableError) as e:
        console.error(str(e))
        logging.error(
            {
                "action": "delete",
                "status": "trash_error",
                "directory": str(dup_dir),
                "error": str(e),
            }
        )
    except OSError as e:
        console.error(f"Error deleting {dup_dir}: {e}")
        logging.error(
            {"action": "delete", "status": "error", "directory": str(dup_dir), "error": str(e)}
        )


def delete_duplicates(
    duplicate_dirs: list[Path],
    dry_run: bool,
    conn: sqlite3.Connection,
    op_root: str = ".",
    *,
    hard_delete: bool = False,
    trash_dir: Optional[str] = None,
) -> None:
    """Removes duplicate directories, quarantining by default.

    Args:
        duplicate_dirs: Directories to remove.
        dry_run: Whether to perform a dry run.
        conn: SQLite database connection.
        op_root: Directory hosting the trash.
        hard_delete: If True, permanently delete instead of quarantining.
        trash_dir: Optional trash location override.
    """
    for dup_dir in duplicate_dirs:
        if dry_run:
            console.status(f"Dry run: would {'delete' if hard_delete else 'quarantine'} {dup_dir}")
            logging.info({"action": "delete", "status": "dry_run", "directory": str(dup_dir)})
            continue
        _remove_or_quarantine_dir(dup_dir, conn, op_root, hard_delete, trash_dir)


def merge_contents(
    base_dir: Path,
    duplicate_dirs: list[Path],
    dry_run: bool,
    conn: sqlite3.Connection,
    op_root: str = ".",
    *,
    hard_delete: bool = False,
    trash_dir: Optional[str] = None,
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
        op_root (str): Directory hosting the trash.
        hard_delete (bool): If True, permanently delete instead of quarantining.
        trash_dir (Optional[str]): Optional trash location override.
    """
    for dup_dir in duplicate_dirs:
        had_conflict = False
        for item in os.listdir(dup_dir):
            src = dup_dir / item
            dst = base_dir / item
            if dst.exists():
                had_conflict = True
                console.warn(f"Conflict: {dst} already exists. Keeping {src}")
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
                    console.status(f"Dry run: would move {src} to {dst}")
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
                        console.status(f"Moving {src} to {dst}")
                        src_is_dir = src.is_dir()
                        shutil.move(str(src), str(dst))
                        logging.info(
                            {
                                "action": "move",
                                "status": "success",
                                "source": str(src),
                                "destination": str(dst),
                            }
                        )
                        if src_is_dir:
                            update_index_after_change(conn, "delete_directory", src)
                            update_index_after_change(conn, "add_directory", dst)
                            scan_tree(dst, conn, recursive=True, level=None, ctx=ScanContext())
                        else:
                            update_index_after_change(conn, "delete_file", src)
                            update_index_after_change(conn, "add_file", dst)
                    except OSError as e:
                        had_conflict = True  # keep the dir; the file did not move
                        console.error(f"Error moving {src} to {dst}: {e}")
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
            console.warn(f"Keeping {dup_dir} (unmerged items remain)")
            logging.info(
                {
                    "action": "delete",
                    "status": "skipped_conflict",
                    "directory": str(dup_dir),
                }
            )
            continue

        if dry_run:
            console.status(f"Dry run: would delete {dup_dir}")
            logging.info({"action": "delete", "status": "dry_run", "directory": str(dup_dir)})
        else:
            _remove_or_quarantine_dir(dup_dir, conn, op_root, hard_delete, trash_dir)
