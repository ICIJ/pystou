# common/safe_extract.py
"""Member-validated archive extraction to prevent path traversal ("zip-slip")."""

import logging
import os
from pathlib import Path
from typing import Optional


def _safe_target(dest: Path, member_name: str) -> Optional[Path]:
    """Returns the resolved target path if it stays inside ``dest``, else None.

    Rejects absolute member names, ``..`` traversal, and members routed through a
    symlinked subdirectory of ``dest``. Symlinks are followed (``os.path.realpath``)
    so containment is checked against where the write would actually land.

    Args:
        dest (Path): Destination directory.
        member_name (str): Archive member name.

    Returns:
        Optional[Path]: The safe target path, or None if the member escapes dest.
    """
    dest_real = os.path.realpath(dest)
    target = os.path.realpath(os.path.join(dest_real, member_name))
    if target == dest_real or target.startswith(dest_real + os.sep):
        return Path(target)
    return None


def safe_extract_zip(zip_ref, dest) -> bool:
    """Extracts a ZIP only if every member stays inside ``dest``.

    By design this is fail-closed: the whole archive is rejected if ANY member is
    unsafe — even members that Python's ``zipfile`` would itself sanitize — so that
    callers never receive a partial extraction from a tampered archive.

    Args:
        zip_ref (zipfile.ZipFile): Open ZIP file.
        dest: Destination directory.

    Returns:
        bool: True if extracted, False if any member was unsafe (nothing written).
    """
    dest = Path(dest)
    for name in zip_ref.namelist():
        if _safe_target(dest, name) is None:
            logging.error(
                {
                    "action": "safe_extract_zip",
                    "status": "unsafe_member",
                    "member": name,
                }
            )
            return False
    zip_ref.extractall(dest)
    return True


def safe_extract_tar(tar_ref, dest) -> bool:
    """Extracts a TAR only if every member is safe (no traversal, no special types).

    Rejects symlink, hardlink, and device/FIFO members, and any member that
    resolves outside ``dest``. Uses ``filter='data'`` on Python 3.12+.

    Args:
        tar_ref (tarfile.TarFile): Open TAR file.
        dest: Destination directory.

    Returns:
        bool: True if extracted, False if any member was unsafe (nothing written).
    """
    dest = Path(dest)
    for member in tar_ref.getmembers():
        if member.issym() or member.islnk() or member.isdev():
            logging.error(
                {
                    "action": "safe_extract_tar",
                    "status": "unsafe_member_type",
                    "member": member.name,
                }
            )
            return False
        if _safe_target(dest, member.name) is None:
            logging.error(
                {
                    "action": "safe_extract_tar",
                    "status": "unsafe_member",
                    "member": member.name,
                }
            )
            return False
    try:
        tar_ref.extractall(dest, filter="data")
    except TypeError:
        # Python < 3.12 has no 'filter' parameter; members already validated above.
        tar_ref.extractall(dest)
    return True
