#!/usr/bin/env python3
"""Main entry point for pystou CLI with subcommands."""

import argparse
import sys

from dedup_folders.main import main as dedup_main, add_dedup_arguments
from unarchive.main import main as unarchive_main, add_unarchive_arguments


def create_parser() -> argparse.ArgumentParser:
    """Creates the main argument parser with subcommands.

    Returns:
        argparse.ArgumentParser: The configured parser.
    """
    parser = argparse.ArgumentParser(
        prog="pystou",
        description="Python scripts for deduplicating folders and unarchiving files.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    subparsers = parser.add_subparsers(
        title="commands",
        dest="command",
        description="Available commands",
    )

    # dedup_folders subcommand
    dedup_parser = subparsers.add_parser(
        "dedup",
        aliases=["dedup_folders"],
        help="Find and deduplicate duplicate folders",
        description="Find and deduplicate folders with similar names.",
    )
    add_dedup_arguments(dedup_parser)
    dedup_parser.set_defaults(func=dedup_main)

    # unarchive subcommand
    unarchive_parser = subparsers.add_parser(
        "unarchive",
        help="Extract archive files",
        description="Find and extract archive files (zip, tar, etc.).",
    )
    add_unarchive_arguments(unarchive_parser)
    unarchive_parser.set_defaults(func=unarchive_main)

    return parser


def main() -> None:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Call the subcommand function with parsed args
    args.func(args)


if __name__ == "__main__":
    main()
