"""Directory validation shared by every subcommand."""

import logging
import sys
from pathlib import Path

from common.errors import InvalidDirectoryError


def validate_directory(directory) -> Path:
    """Validates that ``directory`` exists and is a directory.

    Args:
        directory: Path-like to validate.

    Returns:
        Path: The directory as a ``Path`` (not resolved, to preserve output paths).

    Raises:
        InvalidDirectoryError: If it does not exist or is not a directory.
    """
    path = Path(directory)
    if not path.exists():
        raise InvalidDirectoryError(f"Directory does not exist: {directory}")
    if not path.is_dir():
        raise InvalidDirectoryError(f"Not a directory: {directory}")
    return path


def validate_directory_or_exit(directory) -> Path:
    """Validates a directory, printing a clean error and exiting on failure.

    Preserves the historical CLI behavior (``Error: ...`` to stdout, exit code 1).

    Args:
        directory: Path-like to validate.

    Returns:
        Path: The validated directory.
    """
    try:
        return validate_directory(directory)
    except InvalidDirectoryError as e:
        print(f"Error: {e}", file=sys.stderr)
        logging.error({"action": "error", "message": str(e), "path": str(directory)})
        sys.exit(1)
