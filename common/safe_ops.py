# common/safe_ops.py
"""Safe filesystem operation helpers: non-clobbering paths and verified deletion."""

import logging
from pathlib import Path
from typing import Callable


def unique_path(base) -> Path:
    """Returns ``base`` if free, otherwise appends ' (n)' until a free path is found.

    Args:
        base: Desired path.

    Returns:
        Path: A path that does not currently exist.
    """
    base = Path(base)
    if not base.exists():
        return base
    counter = 1
    while True:
        candidate = Path(f"{base} ({counter})")
        if not candidate.exists():
            return candidate
        counter += 1


def verify_then_delete(archive: Path, success: bool, delete_fn: Callable[[], None]) -> None:
    """Deletes a source archive only if its extraction succeeded.

    Args:
        archive (Path): The source archive.
        success (bool): Whether extraction succeeded and produced output.
        delete_fn (Callable[[], None]): Callback that performs the deletion.
    """
    if not success:
        print(f"Keeping archive (extraction failed or produced nothing): {archive}")
        logging.warning(
            {"action": "keep_archive", "status": "extraction_failed", "archive": str(archive)}
        )
        return
    delete_fn()
