# common/trash.py
"""Reversible deletion: move targets into a co-located, same-volume trash.

Layout under the operation root:

    <op_root>/.pystou-trash/
      runs/<run_id>.jsonl       # write-ahead ledger, one line per moved item
      <run_id>/<n>/<basename>   # the moved files/dirs (n = holding dir)
"""

import contextlib
import json
import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from common.errors import CrossDeviceTrashError, TrashUnavailableError
from common.safe_ops import reserve_unique_name

TRASH_DIR_NAME = ".pystou-trash"


def trash_root(op_root, trash_dir: Optional[str] = None) -> Path:
    """Returns the trash root for an operation (override wins over the default)."""
    if trash_dir:
        return Path(trash_dir)
    return Path(op_root) / TRASH_DIR_NAME


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{secrets.token_hex(2)}"


def _ensure_trash_root(op_root, trash_dir: Optional[str]) -> Path:
    root = trash_root(op_root, trash_dir)
    try:
        (root / "runs").mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise TrashUnavailableError(
            f"Cannot create trash directory at {root}: {e}. "
            f"Use --trash-dir <path> or --hard-delete."
        ) from e
    return root


def _append_jsonl(path: Path, obj: dict) -> None:
    """Appends one JSON line and fsyncs it (write-ahead durability)."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")
        f.flush()
        os.fsync(f.fileno())  # per-item durability: each ledger line survives a crash


def _dir_size(path: Path) -> int:
    total = 0
    for cur, _dirs, files in os.walk(path):
        for name in files:
            with contextlib.suppress(OSError):
                total += os.lstat(os.path.join(cur, name)).st_size
    return total


def _entry_size(path: Path, is_link: bool, kind: str) -> int:
    if is_link:
        return 0
    if kind == "dir":
        return _dir_size(path)
    try:
        return path.stat().st_size
    except OSError:
        return 0


def quarantine(
    items,
    op_root,
    *,
    operation: str,
    command: str,
    trash_dir: Optional[str] = None,
    dry_run: bool = False,
) -> str:
    """Moves ``items`` into the trash, returning the run id ('' on dry run).

    Args:
        items: Iterable of file/dir paths to quarantine.
        op_root: The command's directory argument (hosts ``.pystou-trash``).
        operation: Originating command name (e.g. 'cleanup').
        command: Reconstructed command line, recorded in the ledger header.
        trash_dir: Optional override for the trash root location.
        dry_run: If True, print intentions and move nothing.

    Returns:
        str: The run id, or '' when ``dry_run`` is True or ``items`` is empty.

    Raises:
        TrashUnavailableError: The trash root cannot be created.
        CrossDeviceTrashError: An item lives on a different filesystem.
    """
    items = [Path(p) for p in items]
    if not items:
        return ""
    if dry_run:
        for it in items:
            print(f"Dry run: would quarantine {it}")
        return ""

    root = _ensure_trash_root(op_root, trash_dir)
    root_dev = os.stat(root).st_dev
    # Preflight: refuse the whole run if anything is cross-device (never copy).
    for it in items:
        if os.lstat(it).st_dev != root_dev:
            raise CrossDeviceTrashError(
                f"{it} is on a different filesystem than the trash at {root}. "
                f"Use --trash-dir <path> on the same volume, or --hard-delete."
            )

    run_id = _new_run_id()
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    ledger = root / "runs" / f"{run_id}.jsonl"
    _append_jsonl(
        ledger,
        {
            "_header": True,
            "run_id": run_id,
            "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "command": command,
            "operation": operation,
            "op_root": str(Path(op_root).absolute()),
        },
    )

    for it in items:
        is_link = it.is_symlink()
        kind = "dir" if (it.is_dir() and not is_link) else "file"
        size = _entry_size(it, is_link, kind)
        reserved = reserve_unique_name(run_dir, it.name)
        # WAL invariant: the ledger line is written right after the rename, so the
        # ledger always reflects exactly what was moved. An interrupt leaves at most
        # one moved-but-unrecorded item; restore treats unledgered trash as orphans.
        os.rename(it, reserved)
        _append_jsonl(
            ledger,
            {
                "original": str(it.absolute()),
                "stored": str(reserved.relative_to(root)),
                "size": size,
                "kind": kind,
                "is_symlink": is_link,
            },
        )
        logging.info({"action": "quarantine", "original": str(it.absolute()), "run_id": run_id})
    return run_id
