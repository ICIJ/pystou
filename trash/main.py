#!/usr/bin/env python3
"""Trash subcommand group: list and purge quarantined runs."""

import argparse
import json
import logging
from typing import Annotated, Optional

import typer

from common import console
from common import trash as trashlib
from common.cli import DirectoryArg, LogDirOpt, TrashDirOpt, add_common_arguments
from common.logger import log_configuration, setup_logging
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
        console.status("Trash is empty.")
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


def add_trash_arguments(parser: argparse.ArgumentParser) -> None:
    """Adds the trash subcommand group (list/purge).

    Args:
        parser: ArgumentParser to add arguments to.
    """
    sub = parser.add_subparsers(dest="trash_command", required=True)

    list_p = sub.add_parser("list", help="List quarantine runs")
    add_common_arguments(list_p)
    list_p.add_argument("--json", action="store_true", help="Output JSON")

    purge_p = sub.add_parser("purge", help="Permanently delete quarantined runs")
    add_common_arguments(purge_p)
    purge_p.add_argument("--run", default=None, help="Purge only this run id")
    purge_p.add_argument("--all", action="store_true", help="Purge every run")
    purge_p.add_argument(
        "--older-than",
        type=int,
        default=None,
        metavar="DAYS",
        help="Only purge runs at least DAYS old",
    )
    purge_p.add_argument(
        "--trash-dir", default=None, metavar="PATH", help="Trash location override"
    )


def main(args: Optional[argparse.Namespace] = None) -> None:
    """Main entry point for trash."""
    if args is None:
        parser = argparse.ArgumentParser(description="Manage the PyStou trash.")
        add_trash_arguments(parser)
        args = parser.parse_args()

    setup_logging("trash", args.log_dir)
    log_configuration(args)
    validate_directory_or_exit(args.directory)
    trash_dir = getattr(args, "trash_dir", None)

    if args.trash_command == "list":
        runs = trashlib.list_runs(args.directory, trash_dir)
        if getattr(args, "json", False):
            print(
                json.dumps(
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
                    ],
                    indent=2,
                )
            )
            return
        if not runs:
            print("Trash is empty.")
            return
        for r in runs:
            print(
                f"{r.run_id}  {r.operation:8}  {r.item_count:>5} item(s)  "
                f"{_human_size(r.total_size):>9}  {r.started_at}"
            )
        total = sum(r.total_size for r in runs)
        print(
            f"\n{len(runs)} run(s), {_human_size(total)} reclaimable. "
            f"Use 'pystou trash purge' to free space."
        )
        return

    if args.trash_command == "purge":
        removed = trashlib.purge(
            args.directory,
            run_id=args.run,
            all_runs=args.all,
            older_than_days=args.older_than,
            trash_dir=trash_dir,
        )
        print(f"Purged {removed} run(s).")
        logging.info({"action": "purge_complete", "purged": removed})


if __name__ == "__main__":
    main()
