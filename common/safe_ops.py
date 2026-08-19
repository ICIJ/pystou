# common/safe_ops.py
"""Safe filesystem operation helpers: atomic, non-clobbering path reservation."""

from pathlib import Path


def _unique_candidates(base, *, keep_suffix: bool = False):
    """Yields ``base``, then ``base (1)``, ``base (2)``, ... as Path objects.

    Args:
        base: Desired base path.
        keep_suffix: Place the counter before the file extension
            (``note (1).txt``) instead of after the whole name
            (``note.txt (1)``). In-place renames need the extension preserved;
            trash does not, because quarantined items keep their exact basename.

    Yields:
        Path: Successive non-clobbering candidate paths.
    """
    base = Path(base)
    yield base
    stem, suffix = (base.stem, base.suffix) if keep_suffix else (base.name, "")
    counter = 1
    while True:
        yield base.with_name(f"{stem} ({counter}){suffix}")
        counter += 1


def make_unique_dir(base, *, keep_suffix: bool = False) -> Path:
    """Atomically creates and returns a unique directory.

    Tries to create each candidate with ``mkdir``; on ``FileExistsError`` (the
    name is taken by a directory or a file), retries with the next ' (n)' suffix.

    Args:
        base: Desired directory path.
        keep_suffix: Place the counter before the file extension
            (``note (1).txt``) instead of after the whole name
            (``note.txt (1)``). In-place renames need the extension preserved;
            trash does not, because quarantined items keep their exact basename.

    Returns:
        Path: The freshly created directory.
    """
    candidates = _unique_candidates(base, keep_suffix=keep_suffix)
    while True:
        candidate = next(candidates)
        try:
            candidate.mkdir(parents=True)
            return candidate
        except FileExistsError:
            continue


def reserve_unique_file(base, *, keep_suffix: bool = False) -> Path:
    """Atomically reserves and returns a unique file path.

    Exclusively creates each candidate as an empty file (``O_CREAT | O_EXCL``);
    on ``FileExistsError`` (the name is taken by a file or a directory), retries
    with the next ' (n)' suffix. The returned path exists as an empty file that
    the caller can overwrite.

    Args:
        base: Desired file path.
        keep_suffix: Place the counter before the file extension
            (``note (1).txt``) instead of after the whole name
            (``note.txt (1)``). In-place renames need the extension preserved;
            trash does not, because quarantined items keep their exact basename.

    Returns:
        Path: The freshly reserved (empty) file.
    """
    candidates = _unique_candidates(base, keep_suffix=keep_suffix)
    while True:
        candidate = next(candidates)
        try:
            candidate.touch(exist_ok=False)
            return candidate
        except FileExistsError:
            continue


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
