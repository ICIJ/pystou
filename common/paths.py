"""XDG Base Directory locations PyStou writes to."""

import os
from pathlib import Path

APP_NAME = "pystou"


def log_dir() -> Path:
    """Returns the directory for JSON log files, creating it if needed.

    Logs record what a destructive run did, so they live under the state
    directory rather than the cache: nothing is allowed to wipe them.

    Returns:
        Path: ``$XDG_STATE_HOME/pystou/logs``.
    """
    return _created(_base("XDG_STATE_HOME", ".local/state") / APP_NAME / "logs")


def index_dir() -> Path:
    """Returns the directory for index databases, creating it if needed.

    An index is a snapshot of a scanned tree and can always be rebuilt by
    rescanning, so it belongs in the cache.

    Returns:
        Path: ``$XDG_CACHE_HOME/pystou/index``.
    """
    return _created(_base("XDG_CACHE_HOME", ".cache") / APP_NAME / "index")


def _base(variable: str, fallback: str) -> Path:
    """Reads an XDG base directory from the environment.

    Args:
        variable (str): Name of the XDG environment variable.
        fallback (str): Path relative to the home directory, used when the
            variable is unset or holds a relative path (which the spec
            requires to be ignored).

    Returns:
        Path: The resolved base directory.
    """
    value = os.environ.get(variable, "")
    return Path(value) if os.path.isabs(value) else Path.home() / fallback


def _created(path: Path) -> Path:
    """Creates a directory and returns it.

    Args:
        path (Path): Directory to create.

    Returns:
        Path: The same directory, now guaranteed to exist.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path
