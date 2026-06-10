#!/usr/bin/env python3
"""Main entry point for pystou CLI with subcommands."""

import argparse
import logging
import sys

from cleanup.main import add_cleanup_arguments
from cleanup.main import main as cleanup_main
from common.errors import PystouError
from dedup_folders.main import add_dedup_arguments
from dedup_folders.main import main as dedup_main
from empty.main import add_empty_arguments
from empty.main import main as empty_main
from extract.main import add_extract_arguments
from extract.main import main as extract_main
from identify.main import add_identify_arguments
from identify.main import main as identify_main
from pystou import __version__
from stats.main import add_stats_arguments
from stats.main import main as stats_main


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
        version=f"%(prog)s {__version__}",
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

    # extract subcommand
    extract_parser = subparsers.add_parser(
        "extract",
        help="Extract archive files",
        description="Find and extract archive files (zip, tar, etc.).",
    )
    add_extract_arguments(extract_parser)
    extract_parser.set_defaults(func=extract_main)

    # cleanup subcommand
    cleanup_parser = subparsers.add_parser(
        "cleanup",
        help="Remove junk files (.DS_Store, Thumbs.db, etc.)",
        description="Find and remove junk files from directories.",
    )
    add_cleanup_arguments(cleanup_parser)
    cleanup_parser.set_defaults(func=cleanup_main)

    # identify subcommand
    identify_parser = subparsers.add_parser(
        "identify",
        help="Identify file types and detect issues",
        description="Detect file types and find mismatched extensions or encrypted archives.",
    )
    add_identify_arguments(identify_parser)
    identify_parser.set_defaults(func=identify_main)

    # stats subcommand
    stats_parser = subparsers.add_parser(
        "stats",
        help="Show directory statistics",
        description="Display statistics about files and directories.",
    )
    add_stats_arguments(stats_parser)
    stats_parser.set_defaults(func=stats_main)

    # empty subcommand
    empty_parser = subparsers.add_parser(
        "empty",
        help="Find and remove empty directories",
        description="Find and remove empty directories.",
    )
    add_empty_arguments(empty_parser)
    empty_parser.set_defaults(func=empty_main)

    return parser


def main() -> None:
    """Main entry point with a top-level error boundary."""
    parser = create_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(130)
    except PystouError as e:
        print(f"Error: {e}")
        logging.error({"action": "fatal", "error": str(e)})
        sys.exit(1)
    except Exception as e:
        logging.error({"action": "unexpected_error", "error": str(e)}, exc_info=True)
        print(f"Unexpected error: {e}\nSee the log file for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
