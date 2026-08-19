#!/usr/bin/env python3
"""Restore subcommand: bring quarantined items back to their original paths."""

import logging
import os
from typing import Annotated, Optional

import typer

from common import console, trash
from common.cli import DbDirOpt, DirectoryArg, LogDirOpt, TrashDirOpt
from common.indexer import close_database, initialize_database
from common.logger import setup_logging
from common.validation import validate_directory_or_exit


def restore_command(
    directory: DirectoryArg = ".",
    run: Annotated[Optional[str], typer.Option("--run", help="Restore only this run id.")] = None,
    all_runs: Annotated[bool, typer.Option("--all", help="Restore every run.")] = False,
    path: Annotated[
        Optional[str], typer.Option("--path", help="Restore only the item with this original path.")
    ] = None,
    trash_dir: TrashDirOpt = None,
    log_dir: LogDirOpt = ".",
    db_dir: DbDirOpt = ".",
) -> None:
    """Bring quarantined items back to their original paths."""
    setup_logging("restore", log_dir)
    logging.info(
        {
            "action": "configuration",
            "command": "restore",
            "directory": directory,
            "run": run,
            "all_runs": all_runs,
            "path": path,
            "trash_dir": trash_dir,
        }
    )
    validate_directory_or_exit(directory)

    if not (run or all_runs or path):
        console.status("Specify --run <id>, --all, or --path <original>.")
        return

    conn = None
    db_path = os.path.join(db_dir, "filesystem_index.db")
    if os.path.exists(db_path):
        conn = initialize_database(db_dir)

    restored, conflicted = trash.restore(
        directory,
        run_id=run,
        all_runs=all_runs,
        original_path=path,
        trash_dir=trash_dir,
        conn=conn,
    )
    if conn is not None:
        close_database(conn)

    if restored or conflicted:
        console.success(f"Restored {restored} item(s).")
    else:
        console.status(
            f"Nothing to restore under {trash.trash_root(directory, trash_dir)}."
            " If the run used --trash-dir, pass the same path."
        )
    if conflicted:
        console.warn(f"{conflicted} item(s) left in trash (path occupied or missing).")
    logging.info({"action": "restore_complete", "restored": restored, "conflicted": conflicted})
