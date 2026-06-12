# common/safe_ops.py
"""Safe filesystem operation helpers: non-clobbering paths and verified deletion."""

import logging
from pathlib import Path
from typing import Callable


def _unique_candidates(base):
    """Yields ``base``, then ``base (1)``, ``base (2)``, ... as Path objects.

    Args:
        base: Desired base path.

    Yields:
        Path: Successive non-clobbering candidate paths.
    """
    base = Path(base)
    yield base
    counter = 1
    while True:
        yield Path(f"{base} ({counter})")
        counter += 1


def unique_path(base) -> Path:
    """Returns ``base`` if free, otherwise appends ' (n)' until a free path is found.

    Args:
        base: Desired path.

    Returns:
        Path: A path that does not currently exist.
    """
    return next(candidate for candidate in _unique_candidates(base) if not candidate.exists())


def make_unique_dir(base) -> Path:
    """Atomically creates and returns a unique directory.

    Tries to create each candidate with ``mkdir``; on ``FileExistsError`` (the
    name is taken by a directory or a file), retries with the next ' (n)' suffix.
    This closes the check-then-create race that ``unique_path`` leaves open under
    concurrent extraction.

    Args:
        base: Desired directory path.

    Returns:
        Path: The freshly created directory.
    """
    for candidate in _unique_candidates(base):
        try:
            candidate.mkdir(parents=True)
            return candidate
        except FileExistsError:
            continue


def reserve_unique_file(base) -> Path:
    """Atomically reserves and returns a unique file path.

    Exclusively creates each candidate as an empty file (``O_CREAT | O_EXCL``);
    on ``FileExistsError`` (the name is taken by a file or a directory), retries
    with the next ' (n)' suffix. The returned path exists as an empty file that
    the caller can overwrite. This closes the check-then-create race that
    ``unique_path`` leaves open under concurrent extraction.

    Args:
        base: Desired file path.

    Returns:
        Path: The freshly reserved (empty) file.
    """
    for candidate in _unique_candidates(base):
        try:
            candidate.touch(exist_ok=False)
            return candidate
        except FileExistsError:
            continue


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
            {
                "action": "keep_archive",
                "status": "extraction_failed",
                "archive": str(archive),
            }
        )
        return
    delete_fn()
