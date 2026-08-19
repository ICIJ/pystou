#!/usr/bin/env python3
"""Trash subcommand group: list and purge quarantined runs."""

import logging
from typing import Annotated, Optional

import typer

from common import console
from common import trash as trashlib
from common.cli import DirectoryArg, LogDirOpt, TrashDirOpt
from common.logger import setup_logging
from common.validation import validate_directory_or_exit

trash_app = typer.Typer(help="List or purge quarantined files (.pystou-trash).")


@trash_app.command("list")
def trash_list(
    directory: DirectoryArg = ".",
    json_out: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    trash_dir: TrashDirOpt = None,
    log_dir: LogDirOpt = ".",
) -> None:
    """List quarantine runs."""
    setup_logging("trash", log_dir)
    validate_directory_or_exit(directory)
    runs = trashlib.list_runs(directory, trash_dir)
    if json_out:
        console.print_json(
            [
                {
                    "run_id": r.run_id,
                    "started_at": r.started_at,
                    "command": r.command,
                    "operation": r.operation,
                    "items": r.item_count,
                    "reclaimable_bytes": r.total_size,
                }
                for r in runs
            ]
        )
        return
    if not runs:
        console.status(
            f"No quarantined runs under {trashlib.trash_root(directory, trash_dir)}."
            " If the run used --trash-dir, pass the same path."
        )
        return
    t = console.table("Trash", ["Run", "Op", "Items", "Reclaimable", "Started"])
    for r in runs:
        t.add_row(r.run_id, r.operation, str(r.item_count), _human_size(r.total_size), r.started_at)
    console.print_table(t)
    total = sum(r.total_size for r in runs)
    console.status(
        f"{len(runs)} run(s), {_human_size(total)} reclaimable."
        " Use 'pystou trash purge' to free space."
    )


@trash_app.command("purge")
def trash_purge(
    directory: DirectoryArg = ".",
    run: Annotated[Optional[str], typer.Option("--run", help="Purge only this run id.")] = None,
    all_runs: Annotated[bool, typer.Option("--all", help="Purge every run.")] = False,
    older_than: Annotated[
        Optional[int], typer.Option("--older-than", help="Only purge runs at least DAYS old.")
    ] = None,
    trash_dir: TrashDirOpt = None,
    log_dir: LogDirOpt = ".",
) -> None:
    """Permanently delete quarantined runs."""
    setup_logging("trash", log_dir)
    validate_directory_or_exit(directory)
    removed = trashlib.purge(
        directory,
        run_id=run,
        all_runs=all_runs,
        older_than_days=older_than,
        trash_dir=trash_dir,
    )
    console.success(f"Purged {removed} run(s).")
    logging.info({"action": "purge_complete", "purged": removed})


def _human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"
