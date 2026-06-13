#!/usr/bin/env python3
"""Restore subcommand: bring quarantined items back to their original paths."""

import argparse
import logging
import os
from typing import Optional

from common import trash
from common.cli import add_common_arguments
from common.indexer import close_database, initialize_database
from common.logger import log_configuration, setup_logging
from common.validation import validate_directory_or_exit


def add_restore_arguments(parser: argparse.ArgumentParser) -> None:
    """Adds restore-specific arguments.

    Args:
        parser: ArgumentParser to add arguments to.
    """
    add_common_arguments(parser)
    parser.add_argument("--run", default=None, help="Restore only this run id")
    parser.add_argument("--all", action="store_true", help="Restore every run")
    parser.add_argument(
        "--path", default=None, help="Restore only the item with this original path"
    )
    parser.add_argument("--trash-dir", default=None, metavar="PATH", help="Trash location override")


def main(args: Optional[argparse.Namespace] = None) -> None:
    """Main entry point for restore."""
    if args is None:
        parser = argparse.ArgumentParser(description="Restore quarantined files.")
        add_restore_arguments(parser)
        args = parser.parse_args()

    setup_logging("restore", args.log_dir)
    log_configuration(args)
    validate_directory_or_exit(args.directory)

    if not (args.run or args.all or args.path):
        print("Specify --run <id>, --all, or --path <original>.")
        return

    conn = None
    db_path = os.path.join(args.db_dir, "filesystem_index.db")
    if os.path.exists(db_path):
        conn = initialize_database(args.db_dir)

    restored, conflicted = trash.restore(
        args.directory,
        run_id=args.run,
        all_runs=args.all,
        original_path=args.path,
        trash_dir=getattr(args, "trash_dir", None),
        conn=conn,
    )
    if conn is not None:
        close_database(conn)

    print(f"Restored {restored} item(s).")
    if conflicted:
        print(f"{conflicted} item(s) left in trash (path occupied or missing).")
    logging.info({"action": "restore_complete", "restored": restored, "conflicted": conflicted})


if __name__ == "__main__":
    main()
