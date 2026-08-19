#!/usr/bin/env python3
"""Normalize subcommand: make filenames valid, portable UTF-8 for S3."""

import contextlib
import logging
import os
import shlex
import sys
from enum import Enum
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.table import Table

from common import console
from common.cli import (
    DirectoryArg,
    DryRunOpt,
    LogDirOpt,
    ManifestDirOpt,
    RecursiveOpt,
)
from common.fs_walker import is_excluded_dir
from common.logger import setup_logging
from common.safe_ops import make_unique_dir, reserve_unique_file
from common.trash import new_run_id
from common.validation import validate_directory_or_exit
from normalize import manifest
from normalize.rules import RULES, normalize_name
from pystou import __version__


class Rule(str, Enum):
    utf8 = "utf8"
    nfc = "nfc"
    control = "control"
    punct = "punct"
    all = "all"


def normalize_command(
    directory: DirectoryArg = ".",
    recursive: RecursiveOpt = False,
    undo: Annotated[
        Optional[str], typer.Option("--undo", help="Undo a previous run by its run id.")
    ] = None,
    rule: Annotated[
        Optional[list[Rule]],
        typer.Option("--rule", help="utf8|nfc|control|punct|all (repeatable)."),
    ] = None,
    dry_run: DryRunOpt = False,
    manifest_dir: ManifestDirOpt = None,
    log_dir: LogDirOpt = None,
) -> None:
    """Rename files whose names are not valid, portable UTF-8 (S3-safe)."""
    setup_logging("normalize", log_dir)
    if undo:
        restored, skipped = undo_run(undo, manifest_dir)
        console.success(
            f"Restored {restored} name(s)" + (f", skipped {skipped}" if skipped else "")
        )
        return
    selected = _selected_rules(rule)
    logging.info(
        {
            "action": "configuration",
            "command": "normalize",
            "directory": directory,
            "recursive": recursive,
            "rules": list(selected),
            "dry_run": dry_run,
        }
    )
    root = validate_directory_or_exit(directory)

    run_id = new_run_id()
    path = manifest.manifest_path(run_id, manifest_dir)
    # printable(): a root or argv carrying invalid bytes would otherwise make
    # json.dumps raise UnicodeEncodeError and abort the run before any rename.
    meta = {
        "run": run_id,
        "root": manifest.printable(str(root)),
        "root_b64": manifest.encode(str(root)),
        "argv": manifest.printable(shlex.join(sys.argv)),
        "version": __version__,
        "rules": list(selected),
    }

    renamed, failed, table = _run(root, recursive, selected, dry_run, path, meta)

    if not renamed and not failed:
        console.status("No filenames need normalizing.")
        return
    console.print_table(table)
    if dry_run:
        console.status(
            f"Dry run: would rename {renamed} item(s). "
            "Collision suffixes are resolved at rename time and may differ."
        )
        return
    console.success(f"Renamed {renamed} item(s)" + (f", {failed} failed" if failed else ""))
    console.status(f"Manifest: {path}")


def _selected_rules(rule: Optional[list[Rule]]) -> tuple[str, ...]:
    """Expands the repeatable --rule option, defaulting to every rule."""
    if not rule or Rule.all in rule:
        return RULES
    return tuple(r.value for r in rule)


def _run(
    root: Path,
    recursive: bool,
    rules: tuple[str, ...],
    dry_run: bool,
    path: Path,
    meta: dict,
) -> tuple[int, int, Table]:
    """Walks, renames, and records. Returns (renamed, failed, table)."""
    table = console.table("Renames", ["Old", "New", "Mode"])
    renamed = 0
    failed = 0
    # A dry run must not create a manifest file, not even an empty one.
    writing = manifest.ManifestWriter(path, meta) if not dry_run else contextlib.nullcontext()
    with writing as writer:
        for old, kind in walk_bottom_up(root, recursive):
            new_name, mode, applied = normalize_name(old.name, rules)
            if new_name == old.name:
                continue
            if dry_run:
                table.add_row(manifest.printable(str(old)), new_name, mode)
                renamed += 1
                continue
            try:
                new = apply_rename(old, new_name)
            except OSError as e:
                failed += 1
                console.error(f"Cannot rename {manifest.printable(str(old))}: {e}")
                logging.error(
                    {
                        "action": "rename",
                        "status": "error",
                        "path": manifest.printable(str(old)),
                        "error": str(e),
                    }
                )
                continue
            assert writer is not None
            writer.record(kind, str(old), str(new), mode, applied)
            table.add_row(manifest.printable(str(old)), manifest.printable(str(new)), mode)
            renamed += 1
            logging.info(
                {
                    "action": "rename",
                    "status": "success",
                    "kind": kind,
                    "mode": mode,
                    "old": manifest.printable(str(old)),
                    "new": manifest.printable(str(new)),
                }
            )
    return renamed, failed, table


def walk_bottom_up(root: Path, recursive: bool) -> list[tuple[Path, str]]:
    """Lists everything under ``root``, deepest first, excluding ``root`` itself.

    Children must be renamed while their parent still carries its old name, so
    the manifest replays correctly. ``os.walk(topdown=False)`` cannot be used
    directly because pruning ``dirs`` has no effect once the walk is bottom-up,
    which would descend into ``.pystou-trash``. Walking top-down to prune and
    then reversing gives both.

    Args:
        root: Directory to walk. Never included in the result.
        recursive: Whether to descend past the top level.

    Returns:
        list[tuple[Path, str]]: ``(path, kind)`` pairs, kind being ``file`` or
        ``dir``, ordered so every child precedes its parent.
    """
    walked: list[tuple[Path, list[str], list[str]]] = []
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not is_excluded_dir(d)]
        children = list(dirs)
        if not recursive:
            dirs[:] = []
        walked.append((Path(current), children, files))

    entries: list[tuple[Path, str]] = []
    for folder, dirs, files in reversed(walked):
        for name in files:
            entries.append((folder / name, "file"))
        for name in dirs:
            path = folder / name
            entries.append((path, "file" if path.is_symlink() else "dir"))
    return entries


def apply_rename(old: Path, new_name: str) -> Path:
    """Renames ``old`` to ``new_name`` in place without ever clobbering.

    Bare ``os.rename`` silently replaces an existing file on POSIX, so the
    target is claimed first: an exclusively created empty file, or an
    exclusively created empty directory (which ``rename`` is allowed to
    replace). Symlinks are renamed, never followed.

    Args:
        old: Existing path.
        new_name: Desired basename.

    Returns:
        Path: The path the entry now lives at, which carries a ``' (n)'``
        suffix if the desired name was taken.
    """
    target = old.parent / new_name
    if old.is_dir() and not old.is_symlink():
        claimed = make_unique_dir(target)
    else:
        claimed = reserve_unique_file(target, keep_suffix=True)
    os.rename(old, claimed)
    return claimed


def undo_run(run_id: str, manifest_dir: Optional[str] = None) -> tuple[int, int]:
    """Renames everything in a manifest back to its original name.

    Entries are replayed in reverse (directories before the files they
    contain), which is the order that keeps every recorded path valid.

    An occupied target is skipped rather than suffixed: an undo that invents a
    name is not an undo.

    Args:
        run_id: Run identifier of the manifest to replay.
        manifest_dir: Optional override for the XDG state location.

    Returns:
        tuple[int, int]: ``(restored, skipped)`` counts.
    """
    path = manifest.manifest_path(run_id, manifest_dir)
    _meta, entries = manifest.read(path)
    restored = 0
    skipped = 0
    for entry in reversed(entries):
        source = Path(manifest.decode(entry["new_b64"]))
        target = Path(manifest.decode(entry["old_b64"]))
        if not os.path.lexists(source):
            skipped += 1
            console.warn(f"Missing, cannot undo: {entry['new']}")
            continue
        if os.path.lexists(target):
            skipped += 1
            console.warn(f"Occupied, cannot undo: {entry['old']}")
            continue
        try:
            os.rename(source, target)
        except OSError as e:
            skipped += 1
            console.error(f"Cannot undo {entry['new']}: {e}")
            logging.error(
                {"action": "undo", "status": "error", "path": entry["new"], "error": str(e)}
            )
            continue
        restored += 1
        logging.info(
            {"action": "undo", "status": "success", "old": entry["new"], "new": entry["old"]}
        )
    return restored, skipped
