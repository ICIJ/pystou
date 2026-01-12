import argparse


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
