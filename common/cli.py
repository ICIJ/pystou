import argparse


def parse_arguments(script_name: str) -> argparse.ArgumentParser:
    """Creates and returns an ArgumentParser with common arguments.

    Args:
        script_name (str): The name of the script.

    Returns:
        argparse.ArgumentParser: The configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(description=f"{script_name} script.")
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
    return parser
