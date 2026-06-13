import argparse
from typing import Annotated, Optional

import typer


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    """Adds common arguments to an ArgumentParser.

    Args:
        parser: ArgumentParser to add arguments to.
    """
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to start from (default: current directory)",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recursively process subdirectories",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Perform a dry run (do not make any changes)",
    )
    parser.add_argument(
        "--log-dir",
        default=".",
        help="Directory to store log files (default: current directory)",
    )
    parser.add_argument(
        "--db-dir",
        default=".",
        help="Directory to store index database (default: current directory)",
    )


# Shared Annotated Typer option types for reusable command definitions
DirectoryArg = Annotated[str, typer.Argument(help="Directory to start from (default: current).")]
RecursiveOpt = Annotated[
    bool, typer.Option("-r", "--recursive", help="Recurse into subdirectories.")
]
DryRunOpt = Annotated[bool, typer.Option("-n", "--dry-run", help="Do not make any changes.")]
LogDirOpt = Annotated[str, typer.Option("--log-dir", help="Directory for log files.")]
DbDirOpt = Annotated[str, typer.Option("--db-dir", help="Directory for the index database.")]
TrashDirOpt = Annotated[
    Optional[str],
    typer.Option("--trash-dir", help="Override the trash location (same filesystem)."),
]
HardDeleteOpt = Annotated[
    bool, typer.Option("--hard-delete", help="Permanently delete instead of quarantining.")
]
