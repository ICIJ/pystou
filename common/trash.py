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
import re
import secrets
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from common.errors import CrossDeviceTrashError, TrashUnavailableError
from common.indexer import update_index_after_change
from common.safe_ops import reserve_unique_name

TRASH_DIR_NAME = ".pystou-trash"
_RUN_ID_RE = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]+")


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
            print(f"Dry run: would quarantine {it}", file=sys.stderr)
        return ""

    root = _ensure_trash_root(op_root, trash_dir)
    kept = []
    for it in items:
        if _inside(root, it):
            print(f"Skipping {it}: already quarantined under {root}", file=sys.stderr)
            logging.warning({"action": "quarantine", "status": "already_in_trash", "path": str(it)})
            continue
        kept.append(it)
    items = kept
    if not items:
        return ""

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

    for counter, it in enumerate(items):
        is_link = it.is_symlink()
        kind = "dir" if (it.is_dir() and not is_link) else "file"
        size = _entry_size(it, is_link, kind)
        reserved = reserve_unique_name(run_dir, it.name, counter)
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


@dataclass
class TrashRun:
    run_id: str
    started_at: str
    command: str
    operation: str
    op_root: str
    item_count: int
    total_size: int
    ledger_path: Path


def _read_ledger(ledger_path: Path):
    """Returns (header_dict_or_None, [item_dicts]); tolerates a partial last line."""
    header = None
    items = []
    with open(ledger_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue  # truncated trailing line from an interrupted run
            if obj.get("_header"):
                header = obj
            else:
                items.append(obj)
    return header, items


def list_runs(op_root, trash_dir: Optional[str] = None) -> list[TrashRun]:
    """Lists quarantine runs newest-last (sorted by run id)."""
    root = trash_root(op_root, trash_dir)
    runs_dir = root / "runs"
    runs: list[TrashRun] = []
    if not runs_dir.is_dir():
        return runs
    for ledger in sorted(runs_dir.glob("*.jsonl")):
        header, items = _read_ledger(ledger)
        if header is None:
            continue
        if not _RUN_ID_RE.fullmatch(str(header.get("run_id", ""))):
            logging.warning(
                {"action": "list_runs", "status": "invalid_run_id", "ledger": str(ledger)}
            )
            continue
        runs.append(
            TrashRun(
                run_id=header["run_id"],
                started_at=header.get("started_at", ""),
                command=header.get("command", ""),
                operation=header.get("operation", ""),
                op_root=header.get("op_root", ""),
                item_count=len(items),
                total_size=sum(int(i.get("size", 0)) for i in items),
                ledger_path=ledger,
            )
        )
    return runs


def _inside(root, path: Path) -> bool:
    """True when ``path`` sits under ``root`` (symlinks in the prefix resolved)."""
    resolved = Path(os.path.realpath(path.parent)) / path.name
    return Path(os.path.realpath(root)) in resolved.parents


def _select_runs(runs, run_id, all_runs):
    if run_id is not None:
        return [r for r in runs if r.run_id == run_id]
    if all_runs:
        return runs
    return []


def restore(
    op_root,
    *,
    run_id: Optional[str] = None,
    all_runs: bool = False,
    original_path: Optional[str] = None,
    trash_dir: Optional[str] = None,
    conn=None,
) -> tuple[int, int]:
    """Restores quarantined items to their original paths.

    Reserves-or-refuses on conflict: if an original path is re-occupied, the
    quarantined copy is left in place and counted as a conflict (never clobbered).

    Args:
        op_root: Operation root that hosts the trash.
        run_id: Restore only this run.
        all_runs: Restore every run.
        original_path: Restore only the item whose original matches this path.
        trash_dir: Trash root override.
        conn: Optional sqlite connection; when given, the index is re-populated
            for restored paths.

    Returns:
        tuple[int, int]: (restored_count, conflict_count).
    """
    root = trash_root(op_root, trash_dir)
    runs = _select_runs(
        list_runs(op_root, trash_dir), run_id, all_runs or original_path is not None
    )
    target = str(Path(original_path).absolute()) if original_path else None
    restored = conflicted = 0
    for run in runs:
        _header, items = _read_ledger(run.ledger_path)
        for item in items:
            orig = Path(item["original"])
            if target is not None and str(orig) != target:
                continue
            stored = root / item["stored"]
            if not _inside(root, stored) or not _inside(run.op_root or op_root, orig):
                print(f"Refusing unsafe ledger entry for {orig}", file=sys.stderr)
                logging.warning(
                    {
                        "action": "restore",
                        "status": "unsafe",
                        "stored": str(stored),
                        "original": str(orig),
                    }
                )
                conflicted += 1
                continue
            if os.path.lexists(orig):
                print(
                    f"Conflict: {orig} already exists; leaving quarantined copy",
                    file=sys.stderr,
                )
                logging.warning({"action": "restore", "status": "conflict", "path": str(orig)})
                conflicted += 1
                continue
            if not os.path.lexists(stored):
                print(f"Missing in trash: {stored}", file=sys.stderr)
                logging.warning({"action": "restore", "status": "missing", "stored": str(stored)})
                conflicted += 1
                continue
            orig.parent.mkdir(parents=True, exist_ok=True)
            os.rename(stored, orig)
            restored += 1
            logging.info({"action": "restore", "status": "success", "path": str(orig)})
            if conn is not None:
                _reindex_restore(conn, orig, item.get("kind"), item.get("is_symlink"))
    return restored, conflicted


def _reindex_restore(conn, path: Path, kind, is_symlink) -> None:
    """Re-adds a restored path to the sqlite index (best effort)."""
    if is_symlink:
        return  # symlinks are not indexed as dirs/files
    action = "add_directory" if kind == "dir" else "add_file"
    try:
        update_index_after_change(conn, action, path)
    except sqlite3.Error as e:  # index is a rebuildable cache; never block restore
        logging.warning(
            {
                "action": "reindex_restore",
                "status": "error",
                "path": str(path),
                "error": str(e),
            }
        )


def _run_age_days(run) -> Optional[float]:
    if not run.started_at:
        return None
    try:
        started = datetime.strptime(run.started_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - started).total_seconds() / 86400.0


def purge(
    op_root,
    *,
    run_id: Optional[str] = None,
    all_runs: bool = False,
    older_than_days: Optional[int] = None,
    trash_dir: Optional[str] = None,
) -> int:
    """Permanently deletes selected trash runs. Returns the number purged.

    This is the only operation in PyStou that truly deletes; it is never automatic.

    Args:
        op_root: Operation root that hosts the trash.
        run_id: Purge only this run.
        all_runs: Purge every run (optionally narrowed by ``older_than_days``).
        older_than_days: Only purge runs at least this many days old; a selector
            on its own when neither ``run_id`` nor ``all_runs`` is given.
        trash_dir: Trash root override.
    """
    root = trash_root(op_root, trash_dir)
    runs = list_runs(op_root, trash_dir)
    selected = []
    for run in runs:
        if run_id is not None and run.run_id != run_id:
            continue
        if run_id is None and not all_runs and older_than_days is None:
            continue
        if older_than_days is not None:
            age = _run_age_days(run)
            if age is None or age < older_than_days:
                continue
        selected.append(run)

    count = 0
    for run in selected:
        run_dir = root / run.run_id
        if run_dir.is_dir():
            shutil.rmtree(run_dir)
        if run.ledger_path.exists():
            run.ledger_path.unlink()
        count += 1
        logging.info({"action": "purge", "run_id": run.run_id})
    return count
