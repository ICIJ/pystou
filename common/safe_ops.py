# common/safe_ops.py
"""Safe filesystem operation helpers: non-clobbering paths and verified deletion."""

import logging
import sys
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
    candidates = _unique_candidates(base)
    while True:
        candidate = next(candidates)
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
    candidates = _unique_candidates(base)
    while True:
        candidate = next(candidates)
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
        print(
            f"Keeping archive (extraction failed or produced nothing): {archive}", file=sys.stderr
        )
        logging.warning(
            {
                "action": "keep_archive",
                "status": "extraction_failed",
                "archive": str(archive),
            }
        )
        return
    delete_fn()


def reserve_unique_name(dest_dir, basename, start: int = 0) -> Path:
    """Atomically reserves a collision-free path under ``dest_dir``.

    Creates a numbered holding subdir (``dest_dir/0``, ``dest_dir/1``, ...) with
    ``mkdir`` — the atomic claim — and returns ``<holding>/<basename>``. The
    returned path does not exist yet; its parent is a freshly created empty dir,
    so the caller can ``os.rename`` a file OR a directory into it with no
    collision and no clobber. Works identically for files and directories.

    Args:
        dest_dir: Directory under which to reserve a name.
        basename: Final name the reserved path should carry.
        start: First holding number to try. Callers reserving many names under
            the same directory pass an increasing value, so the probe only runs
            on a real collision instead of rescanning every taken number.

    Returns:
        Path: ``<dest_dir>/<n>/<basename>`` with the ``<n>`` holding dir created.
    """
    dest_dir = Path(dest_dir)
    counter = start
    while True:
        holding = dest_dir / str(counter)
        try:
            holding.mkdir(parents=True)
            return holding / Path(basename).name
        except FileExistsError:
            counter += 1
